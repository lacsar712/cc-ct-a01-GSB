from django.test import TestCase
from ninja.testing import TestClient

from desk.api import api
from desk.auth_utils import hash_password
from desk.models import OffsetSubmission, Tool, User


class DeskAcceptanceTest(TestCase):
    def setUp(self):
        self.client = TestClient(api)
        self.machinist = User.objects.create_user(
            username="machinist",
            password="x",
            role=User.Role.MACHINIST,
        )
        # create_user 会自行哈希，覆盖为项目使用的 bcrypt 密文
        self.machinist.password = hash_password("machine123456")
        self.machinist.save()
        self.auditor = User.objects.create(
            username="auditor",
            password=hash_password("audit123456"),
            role=User.Role.AUDITOR,
        )

    def token(self, username, password):
        resp = self.client.post(
            "/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()["token"]

    def auth(self, token):
        return {"headers": {"Authorization": f"Bearer {token}"}}

    def register(self, token, tool_code, usable=True):
        return self.client.post(
            "/tools",
            json={"tool_code": tool_code, "usable": usable},
            **self.auth(token),
        )

    def test_full_acceptance_flow(self):
        """登甲刀零一勾可投 → 交刀补进待复核 → 摘牌 → 再交整笔退回 → 旧单刀号不变。"""
        token = self.token("machinist", "machine123456")

        # 1) 先登甲刀零一，勾可投
        resp = self.register(token, "甲刀零一", usable=True)
        self.assertEqual(resp.status_code, 200, resp.content)
        tool_id = resp.json()["id"]
        self.assertTrue(resp.json()["usable"])
        self.assertFalse(resp.json()["delisted"])

        # 2) 再交刀补，应进待复核，且刀号锁成甲刀零一
        resp = self.client.post(
            "/submissions",
            json={"tool_id": tool_id, "offset_um": 5},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        first = resp.json()
        self.assertEqual(first["status"], "pending")
        self.assertEqual(first["tool_code"], "甲刀零一")
        self.assertEqual(first["tool_id"], tool_id)
        first_id = first["id"]

        # 3) 把甲刀零一摘牌，写明原因
        resp = self.client.post(
            f"/tools/{tool_id}/delist",
            json={"reason": "刀尖崩损"},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["delisted"])
        self.assertFalse(resp.json()["usable"])
        self.assertEqual(resp.json()["delist_reason"], "刀尖崩损")
        self.assertEqual(resp.json()["delisted_by"], "machinist")

        # 4) 摘牌后再交同刀，应整笔退回并写明原因
        resp = self.client.post(
            "/submissions",
            json={"tool_id": tool_id, "offset_um": 5},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 400)
        msg = resp.json()["detail"]
        self.assertIn("已摘牌", msg)
        self.assertIn("刀尖崩损", msg)
        self.assertIn("整笔退回", msg)
        # 退回不得落单
        self.assertEqual(OffsetSubmission.objects.count(), 1)

        # 5) 打开已过那张单，刀号仍是甲刀零一（锁死快照）
        resp = self.client.get(f"/submissions/{first_id}", **self.auth(token))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["tool_code"], "甲刀零一")
        self.assertEqual(resp.json()["tool_id"], tool_id)

    def test_empty_selection_rejected(self):
        """空选（没点刀）交刀补整笔退回。"""
        token = self.token("machinist", "machine123456")
        resp = self.client.post(
            "/submissions",
            json={"offset_um": 5},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("未从清册点选刀号", resp.json()["detail"])
        self.assertEqual(OffsetSubmission.objects.count(), 0)

    def test_unusable_tool_rejected(self):
        """登刀时没勾可投，交刀补应整笔退回。"""
        token = self.token("machinist", "machine123456")
        resp = self.register(token, "乙刀零二", usable=False)
        self.assertEqual(resp.status_code, 200, resp.content)
        tool_id = resp.json()["id"]

        resp = self.client.post(
            "/submissions",
            json={"tool_id": tool_id, "offset_um": 1},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("未勾可投", resp.json()["detail"])
        self.assertEqual(OffsetSubmission.objects.count(), 0)

    def test_delist_requires_reason_and_is_once(self):
        token = self.token("machinist", "machine123456")
        tool_id = self.register(token, "丙刀零三").json()["id"]

        resp = self.client.post(
            f"/tools/{tool_id}/delist",
            json={"reason": "   "},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 400)

        self.client.post(
            f"/tools/{tool_id}/delist",
            json={"reason": "磨损超标"},
            **self.auth(token),
        )
        resp = self.client.post(
            f"/tools/{tool_id}/delist",
            json={"reason": "再摘一次"},
            **self.auth(token),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Tool.objects.get(pk=tool_id).delist_reason, "磨损超标")

    def test_duplicate_tool_code_rejected(self):
        token = self.token("machinist", "machine123456")
        self.assertEqual(self.register(token, "T01").status_code, 200)
        resp = self.register(token, "T01")
        self.assertEqual(resp.status_code, 400)

    def test_worker_processes_locked_submission(self):
        """已锁死刀号的单据进入待复核后，worker 认领并给出结论。"""
        token = self.token("machinist", "machine123456")
        tool_id = self.register(token, "T01").json()["id"]
        self.client.post(
            "/submissions",
            json={"tool_id": tool_id, "offset_um": 5},
            **self.auth(token),
        )
        row = OffsetSubmission.objects.get()
        self.assertEqual(row.status, OffsetSubmission.Status.PENDING)
        self.assertEqual(row.tool_code, "T01")

        from desk.services import apply_verdict

        apply_verdict(row)
        row.refresh_from_db()
        self.assertEqual(row.status, OffsetSubmission.Status.DONE)
        self.assertEqual(row.verdict, OffsetSubmission.Verdict.PASS)
        self.assertIsNotNone(row.reviewed_at)
        # worker 处理不改变锁死刀号与清册归属
        self.assertEqual(row.tool_code, "T01")
        self.assertEqual(row.tool_id, tool_id)

    def test_auditor_is_read_only(self):
        """复核员可翻清册与锁死刀号，不能改清册也不能交。"""
        m_token = self.token("machinist", "machine123456")
        tool_id = self.register(m_token, "甲刀零一").json()["id"]
        a_token = self.token("auditor", "audit123456")

        # 可翻清册
        resp = self.client.get("/tools", **self.auth(a_token))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

        # 不能登刀
        resp = self.register(a_token, "丁刀零四")
        self.assertEqual(resp.status_code, 403)

        # 不能摘牌
        resp = self.client.post(
            f"/tools/{tool_id}/delist",
            json={"reason": "复核员摘牌"},
            **self.auth(a_token),
        )
        self.assertEqual(resp.status_code, 403)

        # 不能交刀补
        resp = self.client.post(
            "/submissions",
            json={"tool_id": tool_id, "offset_um": 1},
            **self.auth(a_token),
        )
        self.assertEqual(resp.status_code, 403)

        # 可以看单据与锁死刀号
        self.client.post(
            "/submissions",
            json={"tool_id": tool_id, "offset_um": 1},
            **self.auth(m_token),
        )
        resp = self.client.get("/submissions", **self.auth(a_token))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()[0]["tool_code"], "甲刀零一")
