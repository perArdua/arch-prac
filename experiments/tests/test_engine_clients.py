"""
`engine_clients`의 시험.

· 컨테이너 **없을 때**: 빈 목록이 아니라 `EngineUnavailable`이 나는가 (항상 돈다).
· 컨테이너 **있을 때**: 색인 → 넣기 → 질의 왕복이 되는가 (`skipUnless` — SKIP 개수를 끝에 찍는다).

    PYTHONIOENCODING=utf-8 python -B -m unittest discover -s experiments/tests -p "test_engine_clients.py" -v
"""

import http.server
import json
import os
import socket
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine_clients as E                                        # noqa: E402

ABSENT_PG = "memarch-absent-zz"
OS_INDEX = "memarch-test-clients"
PG_TABLE = "memarch_test_clients"
# 질의마다 **둘 이상**이 서로 다른 점수로 맞게 둔다 — 하나만 맞으면 «내림차순» 단언이 공허하게
# 참이 되어 순위를 뒤집어도 시험이 조용했다(심은 위반 M4의 첫 결과).
DOCS = {"d1": "고양이 나비가 창가에서 잔다",
        "d2": "첫 번째 PG사 미팅은 수수료 이견으로 보류됐습니다",
        "d3": "친구랑 AWS 비용을 봤다",
        "d4": "다음 미팅 일정",
        "d5": "나비 사료를 샀다"}


def _strictly_desc(test, hits):
    test.assertGreaterEqual(len(hits), 2, f"공허한 순위 단언 — 맞은 문서가 {len(hits)}개")
    scores = [s for _, s in hits]
    test.assertTrue(all(a > b for a, b in zip(scores, scores[1:])), f"내림차순이 아니다: {hits}")


def _probe(fn):
    try:
        fn()
        return True, ""
    except E.EngineUnavailable as e:
        return False, str(e)


LIVE_OS, WHY_OS = _probe(E.os_require_nori)
LIVE_PG, WHY_PG = _probe(E.pg_require_bigm)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _FakeOS(http.server.BaseHTTPRequestHandler):
    """nori가 **없는** OpenSearch 흉내 — 떠 있지만 플러그인이 없다."""

    def do_GET(self):
        if self.path.startswith("/_cat/plugins"):
            body = [{"name": "n", "component": "opensearch-knn", "version": "2.19.6.0"}]
        else:
            body = {"version": {"number": "2.19.6", "lucene_version": "9.12.3"}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Offline(unittest.TestCase):
    """컨테이너가 없어도 도는 시험 — 조용한 빈 결과를 막는다."""

    def test_os_absent_search_raises_not_empty(self):
        url = f"http://127.0.0.1:{_free_port()}"
        with self.assertRaises(E.EngineUnavailable):
            E.os_search(OS_INDEX, "나비", url=url)

    def test_os_absent_create_and_index_raise(self):
        url = f"http://127.0.0.1:{_free_port()}"
        with self.assertRaises(E.EngineUnavailable):
            E.os_create_index(OS_INDEX, url=url)
        with self.assertRaises(E.EngineUnavailable):
            E.os_index_docs(OS_INDEX, DOCS, url=url)

    def test_os_without_nori_is_unavailable(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), _FakeOS)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with self.assertRaises(E.EngineUnavailable):
                E.os_require_nori(url=f"http://127.0.0.1:{srv.server_port}")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_localhost_refused(self):
        with self.assertRaises(ValueError):
            E.os_request("/", url="http://localhost:19200")

    def test_pg_absent_search_raises_not_empty(self):
        with self.assertRaises(E.EngineUnavailable):
            E.pg_search(PG_TABLE, "나비", container=ABSENT_PG)

    def test_pg_absent_create_and_index_raise(self):
        with self.assertRaises(E.EngineUnavailable):
            E.pg_create_index(PG_TABLE, container=ABSENT_PG)
        with self.assertRaises(E.EngineUnavailable):
            E.pg_index_docs(PG_TABLE, DOCS, container=ABSENT_PG)

    def test_pg_without_bigm_is_unavailable(self):
        with mock.patch.object(E, "psql", return_value=[["0"]]):
            with self.assertRaises(E.EngineUnavailable):
                E.pg_require_bigm()

    def test_provenance_absent_container_raises(self):
        with self.assertRaises(E.EngineUnavailable):
            E.image_provenance(ABSENT_PG, base=E.BASE_IMAGES["memarch-pg"])

    def test_backend_reported(self):
        self.assertEqual(E.PG_BACKEND, "docker-exec-psql")
        self.assertIsInstance(E.PSYCOPG_INSTALLED, bool)


@unittest.skipUnless(LIVE_OS, f"OpenSearch+nori 없음: {WHY_OS}")
class LiveOpenSearch(unittest.TestCase):

    def test_nori_version_matches_engine(self):
        v = E.os_require_nori()
        self.assertEqual(v["analysis-nori"], v["opensearch"])

    def test_image_on_registered_base(self):
        p = E.image_provenance("memarch-os")
        self.assertTrue(p["on_base"], p)
        self.assertEqual(p["extra_layers"], 1)                 # nori 설치 층 하나
        self.assertNotEqual(p["image"], p["base"].split("@")[1])   # ID는 기반과 다르다

    def test_other_opensearch_image_is_not_base(self):
        # 로컬에 따로 있는 2.3.0(F21) — 기반으로 쓰면 «아니다»가 나와야 한다.
        try:
            p = E.image_provenance("memarch-os", base="opensearchproject/opensearch:2.3.0")
        except E.EngineUnavailable:
            self.skipTest("로컬에 opensearch:2.3.0이 없다")
        self.assertFalse(p["on_base"], p)

    def test_nori_strips_particle(self):
        for t in ("나비가", "나비를", "나비는"):
            self.assertEqual(E.os_analyze(t), ["나비"])

    def test_round_trip(self):
        E.os_create_index(OS_INDEX)
        try:
            self.assertEqual(E.os_index_docs(OS_INDEX, DOCS), len(DOCS))
            hits = E.os_search(OS_INDEX, "미팅 보류")
            _strictly_desc(self, hits)
            self.assertEqual(hits[0][0], "d2")          # BM25: 두 항을 다 가진 문서가 위
            self.assertTrue(all(isinstance(i, str) and isinstance(s, float) and s > 0
                                for i, s in hits))
            self.assertEqual({i for i, _ in E.os_search(OS_INDEX, "나비는")}, {"d1", "d5"})
        finally:
            E.os_delete_index(OS_INDEX)


@unittest.skipUnless(LIVE_PG, f"Postgres+pg_bigm 없음: {WHY_PG}")
class LivePostgres(unittest.TestCase):

    def test_image_on_registered_base(self):
        p = E.image_provenance("memarch-pg")
        self.assertTrue(p["on_base"], p)
        self.assertEqual(p["extra_layers"], 1)                 # 확장 파일 복사 층 하나

    def test_round_trip(self):
        E.pg_create_index(PG_TABLE)
        try:
            self.assertEqual(E.pg_index_docs(PG_TABLE, DOCS), len(DOCS))
            hits = E.pg_search(PG_TABLE, "미팅 보류")
            _strictly_desc(self, hits)
            self.assertTrue(all(0 < s <= 1 for _, s in hits))
            # 1위를 클라이언트의 SQL과 **따로 쓴** 질의로 대조한다. (pg_bigm은 max(|A|,|B|) 분모
            # 때문에 짧은 d4를 두 항을 다 가진 긴 d2보다 위에 둔다 — BM25와 반대다.)
            top = E.psql(f"SELECT id FROM {PG_TABLE} "
                         "ORDER BY bigm_similarity(body, '미팅 보류') DESC, id LIMIT 1;")
            self.assertEqual(hits[0][0], top[0][0])
            many = E.pg_search_many(PG_TABLE, ["미팅 보류", "나비는"])
            self.assertEqual(many["미팅 보류"], hits)
            self.assertEqual({i for i, _ in many["나비는"]}, {"d1", "d5"})
        finally:
            E.pg_drop(PG_TABLE)

    def test_missing_table_is_error_not_empty(self):
        with self.assertRaises(E.EngineError):
            E.pg_search("memarch_no_such_table", "나비")


def tearDownModule():
    live = [LiveOpenSearch, LivePostgres]
    total = sum(len([m for m in dir(c) if m.startswith("test_")]) for c in live)
    skipped = sum(len([m for m in dir(c) if m.startswith("test_")])
                  for c, up in zip(live, (LIVE_OS, LIVE_PG)) if not up)
    print(f"\n[engine_clients] 컨테이너가 필요한 시험 {total}개 중 SKIP {skipped}개 "
          f"(OpenSearch+nori {'있음' if LIVE_OS else '없음'} · "
          f"Postgres+pg_bigm {'있음' if LIVE_PG else '없음'}) · psycopg 설치={E.PSYCOPG_INSTALLED}",
          file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
