"""Study lifecycle and canonical records; independent of the web framework."""
import copy
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from research_store import ResearchStore, now
from study_protocol import load_protocol, CONDITIONS, provenance, digest, sus_score
from web_sessions import encode_session, decode_session


class StudyError(ValueError):pass


class StudyRuntime:
    def __init__(self, skills, config, store=None, protocol=None):
        self.protocol=protocol or load_protocol()
        self.store=store or ResearchStore()
        if self.protocol['mode']=='formal' and not self.store.remote:
            raise StudyError('Formal study storage must be external PostgreSQL or Azure SQL')
        self.provenance=provenance(skills,config)
        self.study=self.protocol['id']+':'+self.protocol['version']
        key=self.study
        registered=self.store.get('protocol',key)
        frozen={'protocol':self.protocol,'provenance':self.provenance}
        if registered and registered['data']!=frozen:
            raise StudyError('Study version is frozen. Use a new protocol version after code/configuration changes.')
        if not registered:self.store.put('protocol',key,'researcher',self.study,frozen)

    def active(self,owner):
        if self.store.get('withdrawal',self.study+':'+owner):raise StudyError('You have withdrawn from this study.')

    def information(self,owner):
        self.active(owner)
        enrollment=self.store.get('enrollment',self.study+':'+owner,owner)
        return {'study':self.study,'mode':self.protocol['mode'],
                'information':self.protocol['participant_information'],
                'consent_version':self.protocol['consent_version'],
                'retention_days':self.protocol['retention_days'],
                'contact':self.protocol.get('researcher_contact','Contact the researcher who invited you.'),
                'policy_learning_notice':self.protocol.get('policy_learning_notice',''),
                'initial_assessment':self.protocol.get('initial_assessment',True),
                'enrolled':bool(enrollment),'pre_complete':bool(enrollment and enrollment['data'].get('pre'))}

    def enroll(self,owner,consent,pre,confidence):
        self.active(owner)
        if consent is not True:raise StudyError('Consent is required; you may leave without participating.')
        required=self.protocol.get('initial_assessment',True)
        if required:
            if not isinstance(pre,str) or not 40<=len(pre.strip())<=12000:raise StudyError('Write 40–12,000 characters of your own reasoning.')
            if type(confidence) is not int or not 0<=confidence<=10:raise StudyError('Rate confidence from 0 to 10.')
        else:
            pre,confidence=None,None
        key=self.study+':'+owner
        old=self.store.get('enrollment',key,owner)
        if old:return {'status':'Already enrolled; original participation record retained.'}
        choices=self.protocol['conditions']
        n=int(hmac.new(self.protocol['allocation_seed'].encode(),key.encode(),hashlib.sha256).hexdigest(),16)
        condition=choices[n%len(choices)]
        data={'consented_at':now(),'consent_version':self.protocol['consent_version'],
              'protocol_hash':self.protocol['hash'],'condition':condition,'pre':pre.strip() if required else None,
              'pre_status':'collected' if required else 'not_collected_by_protocol',
              'pre_confidence':confidence,'assessment_version':'reasoning-v1','synthetic':self.protocol['mode']!='formal'}
        self.store.put('enrollment',key,owner,self.study,data)
        return {'status':('Consent and initial assessment saved.' if required else 'Consent saved.')+' You can start the conversation.'}

    def start(self,owner,scenario_id):
        self.active(owner)
        enrollment=self.store.get('enrollment',self.study+':'+owner,owner)
        if not enrollment:
            raise StudyError('Read the study information and save consent'+(' and complete the initial assessment' if self.protocol.get('initial_assessment',True) else '')+' first.')
        # One intervention episode per participant/version avoids silently repeating exposure.
        previous=self.store.records(kind='session',study=self.study,owner=owner)
        if previous and (self.protocol['mode']=='formal' or any(not r['data'].get('ended') for r in previous)):
            raise StudyError('You already have a study conversation. Use Find my conversations to resume it.')
        if scenario_id!='FREEFORM' and self.protocol.get('mode')=='formal':
            raise StudyError('This study uses your own research project.')
        condition=enrollment['data']['condition']
        return {'study':self.study,'protocol':copy.deepcopy(self.protocol),'provenance':self.provenance,
          'condition':condition,'configuration':CONDITIONS[condition].copy(),
          'started_at':now(),'events':[],'revision':0,'synthetic':self.protocol['mode']!='formal'}

    def existing_session(self, owner):
        """Return an active current-version session, or the latest ended one."""
        self.active(owner)

        records = self.store.records(
            kind='session',
            study=self.study,
            owner=owner
        )

        if not records:
            return None

        active = [
            r for r in records
            if not r['data'].get('ended', False)
        ]

        candidates = active if active else records

        candidates.sort(
            key=lambda r: r.get('updated', ''),
            reverse=True
        )

        return candidates[0]['id']

    def sessions(self, owner):
        self.active(owner)
        result=[]
        for record in self.store.records(kind='session',owner=owner):
            current=record['study']==self.study
            if not current and not record['data'].get('research',{}).get('synthetic'):continue
            if self.store.get('withdrawal',record['study']+':'+owner,owner):continue
            result.append({'session_id':record['id'],'study':record['study'],
                'ended':record['data'].get('ended',False),'read_only':not current,
                'updated':record.get('updated','')})
        return sorted(result,key=lambda r:r['updated'],reverse=True)

    def historical_session(self, sid, owner):
        self.active(owner)
        item=self.store.get('session',sid,owner)
        if not item or item['study']==self.study:return None
        if not item['data'].get('research',{}).get('synthetic'):return None
        if self.store.get('withdrawal',item['study']+':'+owner,owner):return None
        sess=decode_session(item['data']);sess['read_only']=True;sess['ended']=True
        return sess

    def save(self,sess,event):
        self.active(sess['owner'])
        research=sess['research']
        research['events'].append(dict(event,at=now()))
        revision=research['revision']
        data=encode_session(sess)
        data['research']['revision']=revision+1
        try:self.store.put('session',sess['session_id'],sess['owner'],research['study'],data,expected=revision)
        except Exception:
            research['events'].pop();raise
        research['revision']=revision+1

    def load(self,id,owner):
        self.active(owner)
        item=self.store.get('session',id,owner)
        if not item or item['study']!=self.study:return None
        return decode_session(item['data'])

    def finish_assessment(self,owner,sid,text,confidence,sus):
        sess=self.load(sid,owner)
        if not sess or not sess['ended']:raise StudyError('End your conversation before completing the final assessment.')
        if not isinstance(text,str) or not 40<=len(text.strip())<=12000:raise StudyError('Write 40–12,000 characters of your own reasoning.')
        if type(confidence) is not int or not 0<=confidence<=10:raise StudyError('Rate confidence from 0 to 10.')
        score=sus_score(sus)
        key=self.study+':'+owner
        previous=self.store.get('post',key,owner)
        if previous and previous['data'].get('session_id')!=sid and self.protocol['mode']!='formal':key+=':'+sid
        if self.store.get('post',key,owner):return {'status':'Final assessment already saved.'}
        self.store.put('post',key,owner,self.study,{'session_id':sid,'text':text.strip(),'confidence':confidence,
              'sus_responses':sus,'sus_score':score,'at':now(),'assessment_version':'reasoning-v1'})
        return {'status':'Final assessment and usability questionnaire saved. Thank you.'}

    def withdraw(self,owner):
        self.active(owner);self.store.withdraw(owner,self.study)
        return {'status':'Participation withdrawn and active study records deleted. Contact the researcher about backup retention.'}


def turn_event(ar,tracker,before,expected,chunks,fired,seconds):
    return {'type':'tutor_turn','stage_before':before,'stage_after':tracker.current_stage,
      'expected_stage':expected,'declared_stage':ar.get('declared_stage'),'stage_complete':ar.get('stage_complete'),
      'action':ar.get('action'),'skill_declared':ar.get('skill_name'),'move_declared':ar.get('tutor_move'),
      'enactment_verified':False,'response_pre_guard':ar.get('response_pre_guard'),
      'guard_modified':ar.get('guard_modified',False),'quality_flags':ar.get('quality_flags',[]),
      'model_trace':ar.get('model_trace',[]),'latency_seconds':round(seconds,3),
      'rag_fired':fired,'rag_sources':[{'source':Path(c.get('source','')).name,'distance':c.get('score'),
         'text_sha256':hashlib.sha256(c.get('text','').encode()).hexdigest()} for c in chunks],
      'stage_state':tracker.summary()}
