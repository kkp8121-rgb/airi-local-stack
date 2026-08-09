#!/usr/bin/env python3
"""Offline, fail-closed production gate for approved AIRI policy-v3 data."""
from __future__ import annotations
import argparse, ctypes, hashlib, json, os, re, stat, sys, unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_VERSION="airi-style-qlora/v3"; SCHEMA_VERSION=3; MIN_REVIEWED_COUNT=200
CATEGORY_TAXONOMY=("banter","commentary","directness","seriousness","truthfulness","warmth")
ALLOWED_SPLITS=("dev","test","train"); MIN_SPLITS={"train":160,"dev":20,"test":20}
FIXTURE_SUITE_ID="airi-c0-s1-evaluation"; FIXTURE_SUITE_VERSION="1.0"
RECORD_FIELDS={"id","split","category","prompt","answer","partition","review","provenance","training_eligible"}
MANIFEST_FIELDS={"schema_version","policy_version","dataset_sha256","human_approved","approved_by","approved_at","reviewed_record_count","categories","reviewer_provenance"}
FIXTURE_FIELDS={"schema_version","suite_id","suite_version","tier","case_id","group","prompt","answer","prompt_sha256","example_sha256"}
REPORT_FIELDS={"schema_version","policy_version","immutable","created_at","dataset_sha256","review_manifest_sha256","c0_fixture_sha256","s1_fixture_sha256","minimum_reviewed_count","reviewed_record_count","splits","categories","reviewer_ids","manifest_approved_by","reviewer_provenance_sha256","fixture_suite","gate"}
ID_RE=re.compile(r"[a-z][a-z0-9_-]{2,79}\Z"); SHA256_RE=re.compile(r"[a-f0-9]{64}\Z"); RFC3339_RE=re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
PLACEHOLDERS={"","admin","anonymous","human-reviewer","n/a","none","reviewer","reviewer-name","tbd","test","todo","unknown"}
PRIVATE_KEY=re.compile(r"(?:user|session|conversation|account|device|token|email|ip|uuid|cookie|password|secret|credential)",re.I); UUID_RE=re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",re.I); EMAIL_RE=re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b"); IP_RE=re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b"); SECRET_RE=re.compile(r"\b(?:bearer\s+[a-z0-9._-]{8,}|(?:api[_-]?key|token|password|secret|session|conversation|account|device)[\s:=]+[^\s]{4,})",re.I)
MARKDOWN_RE=re.compile(r"(^|\n)\s{0,3}(?:[#>*-]\s|\d+[.)]\s)|`{1,3}|\[[^\]]+\]\([^)]*\)"); EMOJI_RE=re.compile("[\U0001F000-\U0001FAFF\U00002700-\U000027BF]")
class GateError(ValueError): pass
@dataclass(frozen=True)
class VerificationResult: report_payload:dict[str,Any]; rows:tuple[dict[str,Any],...]; dataset_sha256:str; manifest_sha256:str; c0_fixture_sha256:str; s1_fixture_sha256:str
def sha256_file(path:Path)->str:
 d=hashlib.sha256()
 with path.open("rb") as h:
  for c in iter(lambda:h.read(1048576),b""): d.update(c)
 return d.hexdigest()
def local_path(path:Path,where:str)->Path:
 if str(path).startswith(("\\\\","//")): raise GateError(f"{where}: UNC/network paths are prohibited")
 p=path.expanduser()
 if p.is_symlink(): raise GateError(f"{where}: symlink paths are prohibited")
 if os.name=="nt" and p.drive and ctypes.windll.kernel32.GetDriveTypeW(f"{p.drive}\\")==4: raise GateError(f"{where}: mapped network drives are prohibited")
 return p.resolve()
def canonical_sha256(value:Any)->str: return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
def prompt_sha256(text:str)->str: return hashlib.sha256(unicodedata.normalize("NFC",text).strip().casefold().encode()).hexdigest()
def _strict(v:Any,fields:set[str],where:str)->dict[str,Any]:
 if not isinstance(v,dict) or set(v)!=fields: raise GateError(f"{where}: object fields must be exactly {sorted(fields)}")
 return v
def _rfc(v:Any,where:str)->str:
 if not isinstance(v,str) or not RFC3339_RE.fullmatch(v): raise GateError(f"{where}: RFC3339 timestamp is required")
 try: assert datetime.fromisoformat(v.replace("Z","+00:00")).tzinfo
 except (ValueError,AssertionError): raise GateError(f"{where}: invalid RFC3339 timestamp")
 return v
def _identity(v:Any,where:str)->str:
 if not isinstance(v,str) or v.strip().casefold() in PLACEHOLDERS or len(v.strip())<3: raise GateError(f"{where}: non-placeholder human identity is required")
 return v.strip()
def _privacy(v:Any,where="value",allow_id=False)->None:
 if isinstance(v,dict):
  for k,x in v.items():
   if not isinstance(k,str) or PRIVATE_KEY.search(k): raise GateError(f"{where}: privacy-sensitive field name is prohibited")
   _privacy(x,f"{where}.{k}",k in {"id","case_id","suite_id","group"})
 elif isinstance(v,list):
  for i,x in enumerate(v): _privacy(x,f"{where}[{i}]")
 elif isinstance(v,str):
  if allow_id and ID_RE.fullmatch(v): return
  if UUID_RE.search(v) or EMAIL_RE.search(v) or IP_RE.search(v) or SECRET_RE.search(v): raise GateError(f"{where}: apparent private data is prohibited")
def _text(v:Any,where:str,*,prompt=False)->str:
 if not isinstance(v,str): raise GateError(f"{where}: must be a string")
 t=unicodedata.normalize("NFC",v).strip(); maximum=280 if prompt else 160; maximum_sentences=3 if prompt else 2
 if not t or len(t)>maximum: raise GateError(f"{where}: length must be 1..{maximum}")
 if any(unicodedata.category(c).startswith("C") for c in t) or EMOJI_RE.search(t) or MARKDOWN_RE.search(t): raise GateError(f"{where}: control characters, emoji, and markdown are prohibited")
 _privacy(t,where)
 if t.count("?")+t.count("？")>1: raise GateError(f"{where}: contains more than one question mark")
 # Terminal punctuation marks delimit sentences; no punctuation is one natural utterance.
 sentences=len([x for x in re.split(r"[.!?。！？]+",t) if x.strip()])
 if sentences>maximum_sentences: raise GateError(f"{where}: too many sentences")
 return t
def _read_json(p:Path,where:str)->dict[str,Any]:
 if not p.is_file() or p.is_symlink(): raise GateError(f"{where}: must be a regular local file")
 try: v=json.loads(p.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as e: raise GateError(f"{where}: invalid JSON") from e
 if not isinstance(v,dict): raise GateError(f"{where}: must contain an object")
 return v
def load_jsonl(p:Path,where:str)->list[dict[str,Any]]:
 if not p.is_file() or p.is_symlink(): raise GateError(f"{where}: must be a regular local JSONL file")
 try: lines=p.read_text(encoding="utf-8").splitlines()
 except OSError as e: raise GateError(f"{where}: cannot read") from e
 if not lines: raise GateError(f"{where}: must not be empty")
 out=[]
 for n,line in enumerate(lines,1):
  if not line.strip(): raise GateError(f"{where}:{n}: blank lines are prohibited")
  try: row=json.loads(line)
  except json.JSONDecodeError as e: raise GateError(f"{where}:{n}: invalid JSON") from e
  if not isinstance(row,dict): raise GateError(f"{where}:{n}: each line must be an object")
  out.append(row)
 return out
def _reviewers(v:Any)->tuple[set[str],str]:
 p=_strict(v,{"review_program","dataset_author","fixture_owner","independent_review","reviewers"},"reviewer_provenance")
 if p["independent_review"] is not True: raise GateError("reviewer_provenance: independent review is required")
 program,author,owner=(_identity(p[k],f"reviewer_provenance.{k}") for k in ("review_program","dataset_author","fixture_owner"))
 if author.casefold()==owner.casefold(): raise GateError("reviewer_provenance: author and fixture owner must be independent")
 if not isinstance(p["reviewers"],list) or not p["reviewers"]: raise GateError("reviewer_provenance.reviewers: at least one reviewer is required")
 ids=set()
 for i,r in enumerate(p["reviewers"]):
  _strict(r,{"id","role","affiliation"},f"reviewers[{i}]"); rid=_identity(r["id"],f"reviewers[{i}].id"); _identity(r["role"],f"reviewers[{i}].role"); _identity(r["affiliation"],f"reviewers[{i}].affiliation")
  if rid.casefold() in {author.casefold(),owner.casefold()} or rid in ids: raise GateError("reviewer_provenance: reviewers must be unique and independent")
  ids.add(rid)
 _privacy(p,"reviewer_provenance"); return ids,canonical_sha256(p)
def validate_manifest(path:Path,digest:str,count:int):
 m=_strict(_read_json(path,"review manifest"),MANIFEST_FIELDS,"review manifest")
 if m["schema_version"]!=SCHEMA_VERSION or m["policy_version"]!=POLICY_VERSION: raise GateError("review manifest: unsupported schema or policy version")
 if not isinstance(m["dataset_sha256"],str) or m["dataset_sha256"]!=digest or not SHA256_RE.fullmatch(m["dataset_sha256"]): raise GateError("review manifest: dataset hash does not match exact bytes")
 if m["human_approved"] is not True: raise GateError("review manifest: explicit human approval is required")
 by=_identity(m["approved_by"],"review manifest.approved_by"); _rfc(m["approved_at"],"review manifest.approved_at")
 if type(m["reviewed_record_count"]) is not int or m["reviewed_record_count"]!=count or count<MIN_REVIEWED_COUNT: raise GateError("review manifest: at least 200 reviewed records are required")
 if m["categories"]!=list(CATEGORY_TAXONOMY): raise GateError("review manifest: category taxonomy must be exact")
 ids,h=_reviewers(m["reviewer_provenance"])
 if by not in ids: raise GateError("review manifest: approved_by must be provenance-bound")
 _privacy(m,"review manifest"); return m,ids,h
def validate_record(row:Any,index:int,reviewers:set[str])->dict[str,Any]:
 r=_strict(row,RECORD_FIELDS,f"record {index}"); _privacy(r,f"record {index}")
 if not isinstance(r["id"],str) or not ID_RE.fullmatch(r["id"]) or r["id"].startswith("seed-"): raise GateError(f"record {index}: id must be non-seed synthetic id")
 if r["split"] not in ALLOWED_SPLITS or r["category"] not in CATEGORY_TAXONOMY: raise GateError(f"record {index}: split/category outside taxonomy")
 _text(r["prompt"],f"record {index}.prompt",prompt=True); _text(r["answer"],f"record {index}.answer")
 p=_strict(r["partition"],{"tier","group"},f"record {index}.partition")
 if p["tier"]!="S1" or not isinstance(p["group"],str) or not ID_RE.fullmatch(p["group"]) or any(x in p["group"].casefold() for x in ("seed","pending","reserved")): raise GateError(f"record {index}: reviewed records must be isolated S1")
 review=_strict(r["review"],{"status","reviewer","approved_at"},f"record {index}.review")
 if review["status"]!="approved" or _identity(review["reviewer"],f"record {index}.review.reviewer") not in reviewers: raise GateError(f"record {index}: explicit bound human approval is required")
 _rfc(review["approved_at"],f"record {index}.review.approved_at")
 provenance=_strict(r["provenance"],{"synthetic","source"},f"record {index}.provenance")
 if provenance["synthetic"] is not True or not isinstance(provenance["source"],str) or not provenance["source"].strip() or any(x in provenance["source"].casefold() for x in ("seed","pending","reserved")): raise GateError(f"record {index}: approved synthetic non-pending provenance required")
 if r["training_eligible"] is not True: raise GateError(f"record {index}: training_eligible must be true")
 return r
def validate_fixture(path:Path,tier:str):
 rows=load_jsonl(path,f"{tier} fixture"); ids=set(); groups=set(); prompts=set()
 for i,row in enumerate(rows,1):
  r=_strict(row,FIXTURE_FIELDS,f"{tier} fixture {i}"); _privacy(r,f"{tier} fixture {i}")
  if r["schema_version"]!=1 or r["suite_id"]!=FIXTURE_SUITE_ID or r["suite_version"]!=FIXTURE_SUITE_VERSION or r["tier"]!=tier: raise GateError(f"{tier} fixture {i}: suite/tier is not canonical")
  if not isinstance(r["case_id"],str) or not ID_RE.fullmatch(r["case_id"]) or not isinstance(r["group"],str) or not ID_RE.fullmatch(r["group"]): raise GateError(f"{tier} fixture {i}: invalid ids")
  q=_text(r["prompt"],f"{tier} fixture {i}.prompt",prompt=True); a=_text(r["answer"],f"{tier} fixture {i}.answer")
  if r["prompt_sha256"]!=prompt_sha256(q) or r["example_sha256"]!=canonical_sha256({"prompt":q,"answer":a}): raise GateError(f"{tier} fixture {i}: hashes do not match")
  if r["case_id"] in ids or r["group"] in groups or r["prompt_sha256"] in prompts: raise GateError(f"{tier} fixture {i}: duplicate case/group/prompt")
  ids.add(r["case_id"]);groups.add(r["group"]);prompts.add(r["prompt_sha256"])
 return rows,ids,groups,prompts
def verify_reviewed_dataset(dataset:Path,review_manifest:Path,c0_fixture:Path,s1_fixture:Path)->VerificationResult:
 dataset,review_manifest,c0_fixture,s1_fixture=(local_path(p,n) for p,n in ((dataset,"dataset"),(review_manifest,"review manifest"),(c0_fixture,"C0 fixture"),(s1_fixture,"S1 fixture")))
 if len({dataset,review_manifest,c0_fixture,s1_fixture})!=4: raise GateError("inputs must be distinct files")
 rows=load_jsonl(dataset,"dataset"); digest=sha256_file(dataset); manifest,reviewers,prov_hash=validate_manifest(review_manifest,digest,len(rows)); c0,c0ids,c0groups,c0prompts=validate_fixture(c0_fixture,"C0"); s1,s1ids,s1groups,s1prompts=validate_fixture(s1_fixture,"S1")
 if c0ids&s1ids or c0groups&s1groups or c0prompts&s1prompts: raise GateError("C0 and S1 fixture suites must be disjoint")
 ids=set();groups=set();prompts=set(); splits={x:0 for x in ALLOWED_SPLITS}; cats={x:0 for x in CATEGORY_TAXONOMY}
 for i,raw in enumerate(rows,1):
  r=validate_record(raw,i,reviewers); rid,g,q=r["id"],r["partition"]["group"],prompt_sha256(r["prompt"])
  if rid in ids or g in groups or q in prompts: raise GateError(f"record {i}: duplicate id, group, or prompt")
  if rid in c0ids|s1ids or g in c0groups|s1groups or q in c0prompts|s1prompts: raise GateError(f"record {i}: evaluation fixture overlap is prohibited")
  ids.add(rid);groups.add(g);prompts.add(q);splits[r["split"]]+=1;cats[r["category"]]+=1
 if any(splits[k]<v for k,v in MIN_SPLITS.items()): raise GateError("dataset split minimums are train>=160/dev>=20/test>=20")
 if any(cats[k]<20 for k in CATEGORY_TAXONOMY): raise GateError("each category requires at least 20 records")
 report={"schema_version":SCHEMA_VERSION,"policy_version":POLICY_VERSION,"immutable":True,"created_at":datetime.now(timezone.utc).isoformat(),"dataset_sha256":digest,"review_manifest_sha256":sha256_file(review_manifest),"c0_fixture_sha256":sha256_file(c0_fixture),"s1_fixture_sha256":sha256_file(s1_fixture),"minimum_reviewed_count":MIN_REVIEWED_COUNT,"reviewed_record_count":len(rows),"splits":splits,"categories":list(CATEGORY_TAXONOMY),"reviewer_ids":sorted(reviewers),"manifest_approved_by":manifest["approved_by"],"reviewer_provenance_sha256":prov_hash,"fixture_suite":{"suite_id":FIXTURE_SUITE_ID,"suite_version":FIXTURE_SUITE_VERSION,"c0_cases":len(c0),"s1_cases":len(s1)},"gate":"approved"}
 return VerificationResult(report,tuple(rows),digest,sha256_file(review_manifest),sha256_file(c0_fixture),sha256_file(s1_fixture))
def write_immutable_report(path:Path,result:VerificationResult)->None:
 path=local_path(path,"gate report")
 if path.exists() or path.is_symlink(): raise GateError("gate report path must not already exist")
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("x",encoding="utf-8",newline="\n") as h: json.dump(result.report_payload,h,ensure_ascii=False,sort_keys=True,separators=(",",":"));h.write("\n")
 os.chmod(path,stat.S_IREAD|stat.S_IRGRP|stat.S_IROTH)
def main()->int:
 p=argparse.ArgumentParser(description="Verify approved AIRI policy-v3 JSONL locally."); p.add_argument("--dataset",type=Path,required=True);p.add_argument("--review-manifest",type=Path,required=True);p.add_argument("--c0-fixture",type=Path,required=True);p.add_argument("--s1-fixture",type=Path,required=True);p.add_argument("--report",type=Path,required=True);a=p.parse_args()
 try: r=verify_reviewed_dataset(a.dataset,a.review_manifest,a.c0_fixture,a.s1_fixture);write_immutable_report(a.report,r)
 except GateError as e: print(f"REJECTED: {e}",file=sys.stderr);return 2
 print(json.dumps(r.report_payload,ensure_ascii=False,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
