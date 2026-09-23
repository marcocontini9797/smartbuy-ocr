import unittest
from document_engine.document_acquisition import acquisition_source, build_document_packages

class WorkflowTests(unittest.TestCase):
    def test_bologna_ape_uses_sace_and_code_alternative(self):
        source = acquisition_source('ape', {'city':'Bologna','ape_code':'123'})
        self.assertIn('sace-er',source['url'])
        self.assertEqual([],source['missing_inputs'])
    def test_other_city_never_gets_bologna_planning_portal(self):
        self.assertIsNone(acquisition_source('agibilita',{'city':'Modena','province':'MO'})['url'])
    def test_unknown_region_does_not_guess_ape_source(self):
        self.assertIsNone(acquisition_source('ape',{})['url'])
    def test_search_reports_missing_inputs(self):
        self.assertEqual(['Foglio','Particella','Subalterno'], acquisition_source('ape',{'city':'Bologna'})['missing_inputs'])
    def test_prepared_draft_remains_copyable(self):
        plan=build_document_packages({'id':1},[],[{'document_type':'ape','status':'open','request_id':'r'}])
        seller=next(g for g in plan['packages'] if g['recipient_role']=='seller')
        self.assertIn('APE completo',seller['draft_message'])
        self.assertEqual('open',seller['items'][0]['status'])
    def test_present_document_not_requested_again(self):
        plan=build_document_packages({'id':1},[{'document_type':'ape','processing_status':'completed'}],[])
        seller=next(g for g in plan['packages'] if g['recipient_role']=='seller')
        self.assertNotIn('APE completo',seller['draft_message'])
        self.assertEqual('present',seller['items'][0]['status'])

if __name__=='__main__': unittest.main()
