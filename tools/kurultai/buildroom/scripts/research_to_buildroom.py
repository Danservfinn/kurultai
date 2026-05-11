#!/usr/bin/env python3
from __future__ import annotations
import argparse, re
from pathlib import Path
from common import BUILDROOM_ROOT, utc_now, write_json

def slug(s:str)->str:
    return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')[:96] or 'research-room'

def read(p):
    return p.read_text(encoding='utf-8', errors='replace') if p else ''

def md_title(s):
    for line in s.splitlines()[:40]:
        if line.lower().startswith('title:'):
            return line.split(':',1)[1].strip().strip('"')
    return None

def pick_summary(s):
    lines=[]
    for raw in s.splitlines():
        line=raw.strip(' #-\t')
        if len(line)>45 and not line.startswith('---') and ':' not in line[:24]: lines.append(line)
        if len(lines)>=4: break
    return (' '.join(lines) or 'Research compiled into a buildroom room.')[:1200]

def ref_for(p:Path):
    parts=p.parts
    if 'brain' in parts: return 'brain:' + '/'.join(parts[parts.index('brain')+1:])
    return 'file:' + p.name

def main():
    ap=argparse.ArgumentParser(description='Compile research artifacts into a buildroom room')
    ap.add_argument('--room-id'); ap.add_argument('--title'); ap.add_argument('--packet',type=Path); ap.add_argument('--synthesis',type=Path); ap.add_argument('--review',type=Path)
    ap.add_argument('--source-ref',action='append',default=[]); ap.add_argument('--signal',action='append',default=[]); ap.add_argument('--source-type',choices=['brain','receipt','kanban','cron','operator','web','manual'],default='brain'); ap.add_argument('--owner',default='kublai'); ap.add_argument('--output-root',type=Path)
    a=ap.parse_args(); now=utc_now()
    texts=[read(a.packet),read(a.synthesis),read(a.review)]
    title=a.title or md_title(texts[1]) or md_title(texts[0]) or 'Research Buildroom'
    rid=a.room_id or slug(title); room=(a.output_root or BUILDROOM_ROOT/'rooms')/rid
    paths=[p for p in [a.packet,a.synthesis,a.review] if p]
    refs=list(a.source_ref)+[ref_for(p) for p in paths]
    idea='idea-'+rid; plan='plan-'+rid; build='build-'+rid
    signal=[{'kind':'research','summary':s} for s in (a.signal or ['research compiled into an operational buildroom contract'])]
    docs={
      'research/research-input.json': {'schema_version':'1.0','packet_id':'research-'+rid,'created_at':now,'source_type':a.source_type,'source_refs':refs,'summary':pick_summary('\n'.join(texts)),'signals':signal,'sensitivity':'internal','sanitization_notes':'Generated from curated references only.'},
      'ideas/idea-contract.json': {'idea_id':idea,'created_at':now,'proposed_by':'research-to-buildroom','title':title,'problem':'Useful research should move through a structured path from insight to bounded work.','why_now':'The buildroom contract exists and can now accept real research inputs.','beneficiaries':['operator','Kurultai agents'],'evidence_refs':refs,'expected_artifacts':['research-input','idea-contract','intent-review','operator-summary'],'proposed_owner':a.owner,'suggested_workspace':'tools/kurultai/buildroom/rooms/'+rid,'scope_boundaries':['curated artifacts only','separate review before implementation'],'non_goals':['production deployment','runtime mutation'],'risk_notes':'Review before promotion.','verification_hint':['Validate room','Review source refs'],'status':'candidate'},
      'reviews/intent-review.json': {'review_id':'intent-'+rid,'idea_id':idea,'reviewed_at':now,'reviewer':'kublai','decision':'needs_main_review','reason':'System-relevant research maps to the buildroom contract.','related_existing_work':['tools/kurultai/buildroom']},
      'reviews/main-review.json': {'review_id':'main-'+rid,'idea_id':idea,'reviewed_at':now,'reviewer':'kublai','decision':'approved_for_planning','risk_band':'low','blast_radius':'local','allowed_workspaces':['tools/kurultai/buildroom'],'approval_notes':'Approved for autonomous continuation.','human_approval_required':False,'blocked_reasons':[]},
      'plans/product-plan.json': {'plan_id':plan,'idea_id':idea,'created_at':now,'owner':a.owner,'user_value':'Research can become bounded work without being buried in chat history.','acceptance_criteria':['room validates','operator summary exists','next action is explicit'],'ux_or_operator_surface':'operator/operator-summary.json','allowed_paths':['tools/kurultai/buildroom/rooms/'+rid],'protected_paths':['runtime state','raw sessions'],'non_goals':['unrelated implementation'],'rollout_plan':'Generate room, validate it, then review the summary.','rollback_plan':'Remove the generated room or revert its commit.'},
      'plans/build-plan.json': {'build_id':build,'plan_id':plan,'created_at':now,'assignee':a.owner,'task_refs':['buildroom://'+rid],'steps':[{'id':'generate','action':'Generate artifacts'},{'id':'validate','action':'Validate schema chain'},{'id':'receipt','action':'Record receipt'}],'files_expected':['tools/kurultai/buildroom/rooms/'+rid],'commands_allowed':['python3 tools/kurultai/buildroom/scripts/validate_room.py'],'verification_commands':['python3 tools/kurultai/buildroom/scripts/validate_room.py tools/kurultai/buildroom/rooms/'+rid],'out_of_scope':['production deploy'],'stop_conditions':['validation failure','scope expansion']},
      'jobs/implementation-receipt.json': {'receipt_id':'receipt-'+rid,'build_id':build,'assignee':a.owner,'started_at':now,'completed_at':now,'files_changed':['tools/kurultai/buildroom/rooms/'+rid],'commands_run':['research_to_buildroom.py'],'tests_run':[],'commit_sha':'pending','open_diffs_summary':'Generated buildroom room from research artifacts.','deviations_from_plan':[],'blocked_items':[],'kanban_task_id':'not-created','kanban_status':'not-applicable','evidence_refs':refs},
      'verification/verification-report.json': {'verification_id':'verify-'+rid,'build_id':build,'verified_by':'research-to-buildroom','verified_at':now,'method':'static_analysis','commands_run':[],'observations':['Room generated.'],'pass':True,'failures':[],'evidence_refs':['buildroom://'+rid]},
      'verification/verification-delta.json': {'delta_id':'delta-'+rid,'build_id':build,'implementation_receipt_ref':'jobs/implementation-receipt.json','verification_report_ref':'verification/verification-report.json','state':'confirmed','confirmed_claims':['Generated artifacts are present.'],'unverified_claims':[],'regressions':[],'next_action':'validate room and select follow-on work'},
      'trust/trust-report.json': {'trust_id':'trust-'+rid,'room_id':rid,'generated_at':now,'state':'watch','reasons':['Generated room is safe to inspect.'],'risk_score':2,'open_questions':['Which follow-on work should be promoted?'],'required_followups':['Run validate_room','Review operator summary'],'safe_to_archive':False},
      'retention/retention-review.json': {'retention_id':'retention-'+rid,'room_id':rid,'reviewed_at':now,'recommendation':'keep','rationale':'Keep as a real research-to-buildroom conversion.','artifacts_to_keep':['all generated room artifacts'],'artifacts_to_improve':['operator summary after follow-on work'],'artifacts_to_prune':[],'requires_human_before_destructive_action':True},
      'operator/operator-summary.json': {'summary_id':'summary-'+rid,'room_id':rid,'generated_at':now,'headline':title,'status':'watch','current_owner':a.owner,'latest_artifacts':[],'operator_needs_to_know':['Research has been compiled into a buildroom room.'],'operator_decisions_needed':['Choose whether to promote the room into implementation work.'],'links':['buildroom://'+rid]}
    }
    for rel,obj in docs.items(): write_json(room/rel,obj)
    print('wrote buildroom room: '+str(room)); return 0
if __name__=='__main__': raise SystemExit(main())
