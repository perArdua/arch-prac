# -*- coding: utf-8 -*-
"""
w6code 지문 (레인 A의 fp.py 사본 — 대상만 같다) — memory.py를 고치기 **전과 후**에 똑같이 돌려 `retrieve()`의 반환을
바이트로 대조한다(사전 등록 ①의 직접 관측). 스위치는 건드리지 않는다 = 기본 경로.

구성 4 (기준칸 + 2단으로 올라간 3셀) × 2단 가중치 2 × 페널티 2 = 16 run.
각 run에서 `Memory.retrieve`의 **모든** 호출을 (질의, [(점수 repr, 요약)], [(요약, 사유)])로 적는다.
네트워크 0 — 임베딩은 캐시에서만. 미스가 있으면 멈춘다.

    PYTHONIOENCODING=utf-8 python -B .omc/notepads/laneA/fp.py OUT.json
"""
import json, os, sys, tempfile
HERE = os.getcwd()
sys.path.insert(0, os.path.join(HERE, "experiments"))
sys.path.insert(0, os.path.join(HERE, "prototype"))
sys.stdout.reconfigure(encoding="utf-8")
import memory as M
from memory import Memory
import precision as P
import rel_dist as RD
import retrieval_sweep as RS

out = sys.argv[1]
tmp = tempfile.mkdtemp(prefix="laneA_fp_")
os.makedirs(os.path.join(tmp, "prototype"))
RS.ROOT = tmp
RD.ROOT = tmp

corpus, ledger, qs = P.load()
key_of = P.key_index(ledger)
scored, _ = P.partition(qs, key_of)
env = (corpus, ledger, qs, scored, key_of)
asks, sums, total = RD.population()
RS.P_N, RS.P_SIG = len(asks) * len(sums), (total, len(sums))
cache, _ = RS.load_cache()
miss = [t for t in dict.fromkeys(asks + sums + [RS.TRAP_UTTERANCE]) if t not in cache]
print("cache miss", len(miss))
if miss:
    raise SystemExit(77)
vals = {
    "lexical": [M.coverage(set(M.bigrams(a)), set(M.bigrams(s))) for a in asks for s in sums],
    "lexical_fixed": [M.jaccard(set(M.tokens_fixed(a)), set(M.tokens_fixed(s))) for a in asks for s in sums],
    "embed": [RD.cos(cache[a], cache[s]) for a in asks for s in sums],
}
G3 = RS.GATES[0]
CFG = [("lexical", 0.80), ("embed", 0.915), ("lexical_fixed", 0.915), ("lexical_fixed", 0.97)]
base_theta = dict(M.THETA_BY_MODE)
rec = {}
orig = Memory.retrieve
log = []

def wrap(self, chat_id, query, now_seq):
    hits, rej = orig(self, chat_id, query, now_seq)
    log.append((query, [(repr(s), r["summary"]) for s, r in hits], list(rej)))
    return hits, rej

snap = RS.snapshot_globals()
Memory.retrieve = wrap
try:
    for mode, f in CFG:
        th = RD.theta_at(vals[mode], f)
        for wr, wi in RS.STAGE2_WEIGHTS:
            for pen in RS.STAGE2_PENALTY:
                c = RS.Cell(0, 2, G3, mode, f, th, RD.actual_cut(vals[mode], th), wr, wi, pen)
                sup = RS.Supplier(cache, force="none")
                RS.apply_cell(c, base_theta, sup)
                RS.guard_theta(c)
                del log[:]
                tot = RS.run_cell(env, c, sup)
                assert not sup.failed and not tot["degraded"] and sup.requests == 0
                key = f"{mode}|{f}|{wr},{wi}|{pen}"
                rec[key] = dict(theta=repr(th), calls=list(log),
                                tot=[tot["ev_hit"], tot["ev_tot"], tot["mis"], tot["ret"],
                                     tot["top1"], tot["top1_n"], len(tot["ties"])])
                print(key, rec[key]["tot"], len(log))
                RS.restore_globals(snap)
finally:
    Memory.retrieve = orig
    RS.restore_globals(snap)
RS.assert_restored(snap, "fp")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(rec, fh, ensure_ascii=False, indent=0, sort_keys=True)
print("wrote", out)
