"""Synthetic evidence fixtures only. No customer/source packets in this repo."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import content_pipeline as p


class PracticalPulseTests(unittest.TestCase):
    def setUp(self):
        self.config = p.load_config(p.ROOT/'content_pulse.config.yml')
        self.at = datetime(2026,10,7,16,tzinfo=timezone.utc)
        source = {'id':'fixture','name':'Synthetic local observation','adapter':'page',
                  'role':'internal_observation','lane':'social_workflows','url':'https://example.com'}
        item = p.make_item(source,'Synthetic approval observation','One recorded batch needed one correction.',
                           None,'2026-10-06T12:00:00-04:00',self.at,self.config['settings'],visibility='internal')
        self.snapshot = {'schema_version':p.SCHEMA_VERSION,'run_id':'synthetic',
                         'config_sha256':p.digest(self.config),'as_of':self.at.isoformat(),
                         'items':[item],'source_health':[],'missing_required_sources':[]}
        self.sign()
        self.ref = item['item_id']
        self.card = {'candidate_id':'candidate-1','title':'Test an approval batch','lane':'social_workflows',
                     'kind':'evergreen','business_task':'Approve a batch','intended_user':'A local operator',
                     'owner_problem':'Review is fragmented','useful_takeaway':'Make the next action visible',
                     'demonstration':'Show a fictional batch','bridge_ninja_connection':'Bounded workflow service',
                     'commercial_evidence':'No buying intent measured','evidence_state':'personally_tested',
                     'local_validation':{'status':'unvalidated','source_refs':[]},'vendor_bias':'None in fixture',
                     'action':'try','source_refs':[self.ref],'claims':[],'unresolved_checks':['Measure operator effort']}

    def sign(self):
        self.snapshot['snapshot_sha256'] = p.digest({k:v for k,v in self.snapshot.items() if k!='snapshot_sha256'})

    def proposal(self, cards=None):
        return {'source_snapshot_sha256':self.snapshot['snapshot_sha256'],
                'candidates':copy.deepcopy([self.card] if cards is None else cards)}

    def validate(self):
        return p.validate_candidates(self.proposal(),self.snapshot,self.config)

    def test_zero_candidates_is_valid(self):
        self.assertFalse(p.validate_candidates(self.proposal([]),self.snapshot,self.config)['publication_ready'])

    def test_packet_limit_and_duplicate_ids(self):
        for cards in [[self.card]*6,[self.card]*2]:
            with self.assertRaises(ValueError): p.validate_candidates(self.proposal(cards),self.snapshot,self.config)

    def test_snapshot_tampering_and_wrong_configuration(self):
        self.snapshot['items'][0]['excerpt']='Changed after retrieval'
        with self.assertRaises(ValueError): self.validate()
        self.sign()
        config=copy.deepcopy(self.config); config['report']['title']='Another desk'
        with self.assertRaises(ValueError): p.validate_snapshot(self.snapshot,config)

    def test_foreign_reference_and_forged_quote(self):
        self.card['source_refs']=['not-in-snapshot']
        with self.assertRaises(ValueError): self.validate()
        self.card['source_refs']=[self.ref]
        self.card['claims']=[{'type':'outcome','source_ref':self.ref,'support_quote':'Imagined success'}]
        with self.assertRaises(ValueError): self.validate()

    def test_local_context_is_not_owner_demand(self):
        self.card['evidence_state']='question_lead'
        self.card['local_validation']={'status':'confirmed','source_refs':[self.ref]}
        self.snapshot['items'][0]['role']='local_context'; self.sign()
        with self.assertRaises(ValueError): self.validate()
        self.snapshot['items'][0]['role']='local_owner_question'; self.sign()
        self.assertEqual(self.validate()['status'],'validated_for_editorial_review')

    def test_vendor_claim_is_not_our_test_or_outcome(self):
        self.snapshot['items'][0]['role']='official_product'; self.sign()
        with self.assertRaises(ValueError): self.validate()
        self.card['evidence_state']='official_documented'
        self.card['claims']=[{'type':'outcome','source_ref':self.ref,'support_quote':'one correction'}]
        with self.assertRaises(ValueError): self.validate()

    def test_prices_need_official_pricing_evidence(self):
        self.card['evidence_state']='question_lead'
        self.snapshot['items'][0]['role']='vendor_guidance'; self.sign()
        self.card['claims']=[{'type':'price','source_ref':self.ref,'support_quote':'one correction'}]
        with self.assertRaises(ValueError): self.validate()

    def test_new_development_needs_primary_dated_evidence(self):
        self.card['kind']='development'
        with self.assertRaises(ValueError): self.validate()
        self.card['evidence_state']='official_documented'
        self.snapshot['items'][0]['role']='official_product'
        self.snapshot['items'][0]['freshness']='reference_only'; self.sign()
        with self.assertRaises(ValueError): self.validate()
        self.snapshot['items'][0]['freshness']='within_window'; self.sign()
        self.validate()

    def test_economic_headline_is_a_question_until_measured(self):
        self.card['title']='Are you overpaying for social content?'
        with self.assertRaises(ValueError): self.validate()
        self.card['kind']='research_question'; self.validate()
        self.card['useful_takeaway']='This saves money for every business'
        with self.assertRaises(ValueError): self.validate()

    def test_savings_need_equivalent_total_costs(self):
        self.card['title']='Save 20% on content'
        comparison={k:'Recorded in fixture' for k in ['currency','period','deliverables','quality_basis',
                    'revision_scope','posting_scope','labor_basis','software_allocation','limitations']}
        comparison.update(baseline_total=100,alternative_total=80,source_refs=[self.ref],same_scope_verified=False)
        self.card['claims']=[{'type':'savings','source_ref':self.ref,'support_quote':'one correction','comparison':comparison}]
        with self.assertRaises(ValueError): self.validate()
        comparison['same_scope_verified']=True; self.validate()
        comparison['labor_basis']=''
        with self.assertRaises(ValueError): self.validate()

    def test_horizon_cannot_dominate_packet(self):
        second=copy.deepcopy(self.card); second['candidate_id']='second'
        self.card['lane']=second['lane']='horizon'
        with self.assertRaises(ValueError): p.validate_candidates(self.proposal([self.card,second]),self.snapshot,self.config)

    def test_dates_use_utc_and_reject_naive_time(self):
        self.assertEqual(p.timestamp('2026-10-07T08:00:00-04:00').hour,12)
        with self.assertRaises(ValueError): p.timestamp('2026-10-07T12:00:00')

    def test_page_retrieval_is_not_a_publication_date(self):
        source=self.config['sources'][3]
        getter=lambda *_: (b'<title>Reference</title><nav>Ignore menu</nav><script>Ignore script</script><p>'+b'useful reference '*20+b'</p>',source['url'])
        item=p.fetch_source(source,self.config['settings'],self.at,getter)[0]
        self.assertEqual(item['freshness'],'reference_only')
        self.assertIsNone(item['published_at'])
        self.assertNotIn('Ignore',item['excerpt'])

    def test_quiet_feed_and_failed_feed_are_distinct(self):
        config=copy.deepcopy(self.config); config['sources']=[config['sources'][0]]
        empty=lambda *_: (b'<rss version="2.0"><channel><title>Empty</title></channel></rss>','https://example.com')
        packet=p.fetch(config,self.at,getter=empty)
        self.assertEqual(packet['source_health'][0]['state'],'healthy_no_current_items')
        bad=lambda *_: (b'<html>Not a feed</html>','https://example.com')
        self.assertEqual(p.fetch(config,self.at,getter=bad)['source_health'][0]['state'],'failed')

    def test_stale_and_future_feed_entries_are_excluded(self):
        xml=b'<rss version="2.0"><channel><title>Fixture</title><item><title>Old</title><link>https://example.com/old</link><pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate></item><item><title>Future</title><link>https://example.com/future</link><pubDate>Thu, 08 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(p.fetch_source(self.config['sources'][0],self.config['settings'],self.at,lambda *_:(xml,'https://example.com')),[])

    def test_same_url_changed_text_gets_new_identity(self):
        item=copy.deepcopy(self.snapshot['items'][0])
        source={'id':'fixture','name':'Fixture','role':'internal_observation','lane':'social_workflows'}
        changed=p.make_item(source,item['title'],'Changed content',item['url'],item['published_at'],self.at,self.config['settings'])
        self.assertNotEqual(changed['item_id'],item['item_id'])

    def test_question_filter_preserves_relevant_leads_and_source_limit(self):
        source=copy.deepcopy(self.config['sources'][0]); source['max_items']=1
        xml=b'<rss version="2.0"><channel><title>Fixture</title><item><title>Unrelated thought</title><link>https://example.com/a</link></item><item><title>Customer email approvals</title><link>https://example.com/b</link></item><item><title>Social content planning</title><link>https://example.com/c</link></item></channel></rss>'
        items=p.fetch_source(source,self.config['settings'],self.at,lambda *_:(xml,'https://example.com'))
        self.assertEqual([i['url'] for i in items],['https://example.com/b'])

    def test_private_path_blocks_repository_and_symlink(self):
        with self.assertRaises(ValueError): p.private_output(p.ROOT/'reports/private.json')
        with tempfile.TemporaryDirectory() as directory:
            link=Path(directory)/'repo'; link.symlink_to(p.ROOT,target_is_directory=True)
            with self.assertRaises(ValueError): p.private_output(link/'private.json')

    def test_private_intake_cannot_be_publication_permission(self):
        row={'record_id':'synthetic','title':'Question','excerpt':'Synthetic question','source_locator':'private fixture',
             'observed_at':'2026-10-06T12:00:00Z','lane':'owner_needs','role':'local_owner_question',
             'visibility':'internal','publication_permission':'granted'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'intake.json'; path.write_text(json.dumps({'schema_version':'2.0','items':[row]}))
            with self.assertRaises(ValueError): p.load_intake(path,self.config['sources'][-1],self.config['settings'],self.at)
            row['publication_permission']='not_granted'; row['observed_at']='2026-10-08T12:00:00Z'
            path.write_text(json.dumps({'schema_version':'2.0','items':[row]}))
            with self.assertRaises(ValueError): p.load_intake(path,self.config['sources'][-1],self.config['settings'],self.at)

    def test_missing_required_local_intake_blocks_synthesis(self):
        config=copy.deepcopy(self.config); config['sources']=[config['sources'][-1]]
        packet=p.fetch(config,self.at,public_only=True)
        self.assertEqual(packet['missing_required_sources'],['private-local-intake'])
        client=Mock()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): p.synthesize(packet,config,1,Path(directory)/'receipt.json',client)
        client.messages.create.assert_not_called()

    def test_budget_and_stale_rates_block_paid_request(self):
        client=Mock(); client.messages.count_tokens.return_value=SimpleNamespace(input_tokens=100)
        with tempfile.TemporaryDirectory() as directory, patch.object(p,'now',return_value=self.at):
            path=Path(directory)/'receipt.json'
            for budget in [0,0.001,float('nan'),float('inf')]:
                with self.assertRaises(ValueError): p.synthesize(self.snapshot,self.config,budget,path,client)
        client.messages.create.assert_not_called()
        with tempfile.TemporaryDirectory() as directory, patch.object(p,'now',return_value=datetime(2026,12,7,tzinfo=timezone.utc)):
            with self.assertRaises(ValueError): p.synthesize(self.snapshot,self.config,1,Path(directory)/'receipt.json',client)

    def test_unknown_paid_outcome_prevents_blind_retry(self):
        client=Mock(); client.messages.count_tokens.return_value=SimpleNamespace(input_tokens=100)
        client.messages.create.side_effect=TimeoutError('Unknown acceptance')
        with tempfile.TemporaryDirectory() as directory, patch.object(p,'now',return_value=self.at):
            path=Path(directory)/'receipt.json'
            with self.assertRaises(TimeoutError): p.synthesize(self.snapshot,self.config,1,path,client)
            self.assertEqual(p.read(path)['state'],'attempt_started_outcome_unknown')
            with self.assertRaises(ValueError): p.synthesize(self.snapshot,self.config,1,path,client)
            self.assertEqual(client.messages.create.call_count,1)

    def test_html_escapes_source_and_candidate_text(self):
        self.card['title']='<script>alert(1)</script>'
        output=p.render(self.validate(),self.snapshot)
        self.assertNotIn('<script>',output)
        self.assertIn('&lt;script&gt;',output)
        self.assertIn('Not approved for publication',output)

    def test_paid_response_is_recoverable_even_if_json_is_invalid(self):
        client=Mock();client.messages.count_tokens.return_value=SimpleNamespace(input_tokens=100)
        client.messages.create.return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='Invalid JSON')],
                usage=SimpleNamespace(input_tokens=100,output_tokens=3),stop_reason='end_turn')
        with tempfile.TemporaryDirectory() as directory, patch.object(p,'now',return_value=self.at):
            path=Path(directory)/'receipt.json'
            with self.assertRaises(json.JSONDecodeError): p.synthesize(self.snapshot,self.config,1,path,client)
            self.assertEqual(p.read(path)['response_text'],'Invalid JSON')
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_attempt_reservation_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'receipt.json'
            p.reserve_receipt(path,{'attempt':1})
            with self.assertRaises(FileExistsError): p.reserve_receipt(path,{'attempt':2})
            self.assertEqual(p.read(path)['attempt'],1)


if __name__=='__main__':
    unittest.main()
