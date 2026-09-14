# -*- coding: utf-8 -*-
"""
test_vecdim_ppr_probe.py — ❔1·❔2 판정이 **뒤집힐 수 있는가**를 심어서 본다.

«코드는 차원을 안 본다» · «축 태깅이 없다»는 둘 다 **없음**의 주장이라, 검사가 원래 0만
내는 것이라면 발화할 수 없는 검사다. 그래서 차원 리터럴 · 엄격한 코사인 · 엄격한 저장 ·
축 표지를 하나씩 심어 판정 도구가 그것을 잡는지 본다. 원본은 안 건드린다 — 파일은 `%TEMP%`
복사본에, 함수는 런타임 재바인딩(`try/finally` 복원)으로 심는다.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import vecdim_ppr_probe as V  # noqa: E402
import memory as M  # noqa: E402
import embedding  # noqa: E402


class ProtoCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vecdim_t_"))
        for p in V.PROTO.rglob("*.py"):
            shutil.copy(p, self.tmp / p.name)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _append(self, name, text, marker):
        p = self.tmp / name
        src = p.read_text(encoding="utf-8")
        self.assertEqual(src.count(marker), 0)
        p.write_text(src + text, encoding="utf-8")
        self.assertEqual(p.read_text(encoding="utf-8").count(marker), 1)

    def test_real_1024_are_all_byte_units(self):
        self.assertTrue(all(k == "바이트 단위" for _, _, k, _ in V.classify_1024()))

    def test_planted_dim_literal_is_caught(self):
        self._append("embedding.py", "\nEMBED_DIM = 1024\n", "EMBED_DIM = 1024")
        kinds = [k for f, _, k, _ in V.classify_1024(self.tmp) if f == "embedding.py"]
        self.assertIn("그 밖", kinds)

    def test_axis_tag_planted_fires_and_substring_is_silent(self):
        self._append("memory.py", '\n_NOTE = "개인정보 삭제는 인정 못 한다"\n', "인정 못 한다")
        self.assertEqual(sum(map(len, V.axis_grep(sorted(self.tmp.glob("*.py"))).values())), 0)
        self._append("memory.py", '\n_AXIS = "(배려)"\n', '"(배려)"')
        self.assertGreaterEqual(
            sum(map(len, V.axis_grep(sorted(self.tmp.glob("*.py"))).values())), 1)


class RuntimeTest(unittest.TestCase):
    def test_cosine_verdict_flips(self):
        # 🔄 w6code (docs/17 축-2) — 옛 이름 `test_strict_cosine_flips`. 옛 시험은 «받는다»를 먼저
        #    단언하고 엄격한 코사인을 심어 뒤집었다. `_cosine`이 이제 던지므로 방향이 반대다:
        #    «거절한다»를 단언하고 옛 코사인(`zip`이 조용히 끊는 것)을 심어 뒤집는다.
        self.assertFalse(V.cosine_accepts_mismatch()[0])
        orig = M._cosine

        def lenient(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            return dot / ((sum(x * x for x in a) ** 0.5 or 1.0) * (sum(x * x for x in b) ** 0.5 or 1.0))
        try:
            M._cosine = lenient
            self.assertTrue(V.cosine_accepts_mismatch()[0])
        finally:
            M._cosine = orig
        self.assertIs(M._cosine, orig)

    def test_degrade_verdict_flips(self):
        # 🆕 w6code — ②″. 차원 대조(`_dims_agree`)를 항등으로 심으면 강등 대신 예외가 샌다.
        ok, kinds = V.retrieve_degrades_on_mismatch()
        self.assertTrue(ok)
        self.assertEqual((kinds.count("dim_mismatch"), kinds.count("degraded")), (1, 1))
        orig = M._dims_agree
        try:
            M._dims_agree = lambda notes, qv, dvecs: (qv, dvecs)
            ok, why = V.retrieve_degrades_on_mismatch()
            self.assertFalse(ok)
            self.assertIn("DimMismatch", why)
        finally:
            M._dims_agree = orig
        self.assertIs(M._dims_agree, orig)

    def test_strict_store_flips(self):
        self.assertEqual(V.vec_roundtrip(), (True, 3))
        orig = embedding.db_put_vec

        def strict(db, chat_id, text, vec, model=embedding.EMBED_MODEL):
            if len(vec) != 1024:
                raise ValueError("1024차원만 받는다")
            return orig(db, chat_id, text, vec, model)
        try:
            embedding.db_put_vec = strict
            self.assertFalse(V.vec_roundtrip()[0])
        finally:
            embedding.db_put_vec = orig
        self.assertIs(embedding.db_put_vec, orig)

    def test_render_with_tags_is_caught(self):
        rows = V.render_probe()
        self.assertTrue(any(r[2] > 0 for r in rows))          # 검색이 돌았다
        self.assertTrue(all(r[3] == 0 for r in rows))
        orig = M.Context.render
        try:
            M.Context.render = lambda self: orig(self) + "\n· 나비 (배려)"
            self.assertTrue(all(r[3] >= 1 for r in V.render_probe()))
        finally:
            M.Context.render = orig
        self.assertIs(M.Context.render, orig)


if __name__ == "__main__":
    unittest.main()
