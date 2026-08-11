import os, sqlite3, tempfile, time, unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from airi_memory import (
    MemoryStore,
    NameScanner,
    assemble_context,
    pack_vector,
    render_memory_placeholders,
    unpack_vector,
)

class E:
    def __init__(self): self.calls=0
    def encode(self, texts): self.calls += 1; return [[1.,0.] for _ in texts]

class MemoryTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix='.db'); os.close(fd); self.e=E(); self.s=MemoryStore(self.db,self.e)
    def tearDown(self): os.unlink(self.db)
    def test_schema_and_null_vector(self):
        self.s.embedder=None; x=self.s.add_item(kind='entity',subtype='person',name='Ada',content='person'); self.assertIsNone(self.s.active_rows(None)[0]['vector']); self.assertTrue(self.s.health()['ok'])

    def test_deadline_returns_distinct_timeout_state(self):
        self.s.add_item(kind='entity', subtype='person', name='Ada', content='Ada', vector=pack_vector([1., 0.]))
        result = self.s.retrieve(None, 'who is Ada?', deadline=time.monotonic() - .001)
        self.assertEqual(result.status, 'timed_out')
        self.assertTrue(result.failed)
        self.assertEqual(result.block, '')

    def test_vector_score_cache_is_version_scoped_and_lru_bounded(self):
        self.s.add_item(kind='entity', subtype='person', name='Ada', content='Ada', vector=pack_vector([1., 0.]))
        rows = self.s.active_rows(None, 'entity')
        version = self.s.health()['data_version']
        first = self.s._vector_scores([1., 0.], rows, str(version), ('scope',), lambda: None)
        self.assertAlmostEqual(first[int(rows[0]['id'])], 1.0, places=6)
        self.s.add_item(kind='entity', subtype='person', name='Bea', content='Bea', vector=pack_vector([0., 1.]))
        next_rows = self.s.active_rows(None, 'entity')
        second = self.s._vector_scores([1., 0.], next_rows, str(self.s.health()['data_version']), ('scope',), lambda: None)
        self.assertEqual(len(second), 2)
        self.assertEqual(len(self.s._vector_score_cache), 2)

    def test_act_control_is_saved_as_private_event_not_dialogue(self):
        raw = '<|ACT {"mood":"calm"}|> Hello there'
        self.s.append_turn('room', 'private user text', raw, 1)
        with self.s._session() as connection:
            dialogue = connection.execute(
                "SELECT role,content FROM conversation_message WHERE session_id=? ORDER BY id", ('room',)
            ).fetchall()
            events = connection.execute(
                "SELECT kind,payload FROM conversation_event WHERE session_id=?", ('room',)
            ).fetchall()
        self.assertEqual([(row['role'], row['content']) for row in dialogue],
                         [('user', 'private user text'), ('assistant', 'Hello there')])
        self.assertEqual([(row['kind'], row['payload']) for row in events],
                         [('assistant_control', '<|ACT {"mood":"calm"}|>')])
        self.assertNotIn('private user text', repr(self.s.health()))

    def test_memory_placeholder_rendering_preserves_storage_and_selects_particles(self):
        source='{{user}}은 {{char}}으로 갔고 {{user}}가 {{user}}를 도왔다. {{user}}와 약속했다.'
        rendered=render_memory_placeholders(source,user_name='민석',char_name='아이리')
        self.assertEqual(rendered,'민석은 아이리로 갔고 민석이 민석을 도왔다. 민석과 약속했다.')
        self.assertEqual(source,'{{user}}은 {{char}}으로 갔고 {{user}}가 {{user}}를 도왔다. {{user}}와 약속했다.')
        self.assertEqual(render_memory_placeholders('{{user}}으로',user_name='하늘'),'하늘로')
        self.assertEqual(render_memory_placeholders('{{user}}는',user_name=None),'{{user}}는')
        self.assertEqual(render_memory_placeholders('{{user}}이야 {{user}}이가',user_name='세리'),'세리야 세리가')
        self.assertEqual(render_memory_placeholders('{{user}}이야 {{user}}이가',user_name='민석'),'민석이야 민석이가')
        self.assertEqual(render_memory_placeholders('{{user}}야 {{user}}가',user_name='민석'),'민석아 민석이')
        self.assertEqual(render_memory_placeholders('{{user}}이야기',user_name='세리'),'세리이야기')

    def test_curated_canon_ingest_is_idempotent_and_preserves_replacement_history(self):
        bundle={
            'schema_version':1,
            'entities':[
                {'key':'airi','subtype':'person','name':'아이리','content':'밝은 친구'},
                {'key':'user','subtype':'person','name':'{{user}}','content':'대화 상대'},
            ],
            'facts':[
                {'key':'airi.tone','subtype':'trait','content':'아이리는 자연스러운 반말을 쓴다.','subjects':['airi']},
            ],
            'relations':[
                {'key':'airi.user.friend','subtype':'친구','content':'아이리와 {{user}}는 함께 대화하는 친구다.','source':'airi','target':'user'},
            ],
        }
        first=self.s.ingest_canon_bundle(bundle)
        second=self.s.ingest_canon_bundle(bundle)
        self.assertEqual(first,{'total':4,'inserted':4,'replaced':0,'unchanged':0})
        self.assertEqual(second,{'total':4,'inserted':0,'replaced':0,'unchanged':4})
        old_airi=next(row for row in self.s.active_rows(None,'entity') if row['name']=='아이리')
        changed=__import__('copy').deepcopy(bundle); changed['entities'][0]['content']='더 밝고 호기심 많은 친구'
        result=self.s.ingest_canon_bundle(changed)
        self.assertEqual(result,{'total':4,'inserted':0,'replaced':1,'unchanged':3})
        new_airi=next(row for row in self.s.active_rows(None,'entity') if row['name']=='아이리')
        self.assertNotEqual(old_airi['id'],new_airi['id'])
        with self.s._session() as connection:
            history=connection.execute('SELECT status,superseded_by FROM memory WHERE id=?',(old_airi['id'],)).fetchone()
            fact_subject=connection.execute('SELECT entity_id FROM fact_subject').fetchone()[0]
            relation_source=connection.execute("SELECT source_id FROM memory WHERE kind='relation' AND status='active'").fetchone()[0]
        self.assertEqual((history['status'],history['superseded_by']),('superseded',new_airi['id']))
        self.assertEqual((fact_subject,relation_source),(new_airi['id'],new_airi['id']))
        self.assertTrue(all(row['source']=='base' for row in self.s.active_rows(None)))

    def test_invalid_canon_bundle_rolls_back_without_partial_rows(self):
        invalid={
            'schema_version':1,
            'entities':[{'key':'airi','subtype':'person','name':'아이리','content':'친구'}],
            'facts':[{'key':'bad','subtype':'trait','content':'잘못된 참조','subjects':['missing']}],
            'relations':[],
        }
        with self.assertRaises(ValueError): self.s.ingest_canon_bundle(invalid)
        self.assertEqual(self.s.active_rows(None),[])
    def test_ops_and_rollback(self):
        a=self.s.add_item(kind='entity',subtype='person',name='A',content='a'); out=self.s.apply_operations('s',[{'op':'ADD_ENTITY','sourceTurnNumber':1,'alias':'e1','subtype':'person','name':'B','content':'b','turnRange':None,'reason':None}],{'e0':a}); self.assertIn('e1',out)
        with self.assertRaises(ValueError): self.s.apply_operations('s',[{'op':'ADD_FACT','sourceTurnNumber':1,'alias':'f2','subtype':'trait','content':'bad','subjectAliases':['missing'],'turnRange':[1,1],'reason':None}],out)
        self.assertEqual(len(self.s.active_rows('s','fact')),0)
    def test_operation_embeddings_are_batched_before_the_write_transaction(self):
        before=self.e.calls
        operations=[
            {'op':'ADD_ENTITY','sourceTurnNumber':1,'alias':'e0','subtype':'person','name':'A','content':'alpha','turnRange':None,'reason':None},
            {'op':'ADD_ENTITY','sourceTurnNumber':1,'alias':'e1','subtype':'person','name':'B','content':'beta','turnRange':None,'reason':None},
        ]
        self.s.apply_operations('s',operations,{})
        self.assertEqual(self.e.calls-before,1)
    def test_stage_b_candidates_include_fact_and_relation_endpoint_aliases(self):
        a=self.s.add_item(kind='entity',subtype='person',name='Alpha',content='first person')
        b=self.s.add_item(kind='entity',subtype='person',name='Beta',content='second person')
        self.s.add_item(kind='fact',subtype='trait',content='needle fact',subject_ids=[a])
        self.s.add_item(kind='relation',subtype='friend',content='needle relation',source_id=a,target_id=b)
        candidates,aliases=self.s.build_stage_b_candidates(None,[{'content':'needle'}],limit=2)
        fact=next(item for item in candidates if item['kind']=='fact')
        relation=next(item for item in candidates if item['kind']=='relation')
        self.assertTrue(fact['subjectAliases'])
        self.assertIsNotNone(relation['sourceAlias'])
        self.assertIsNotNone(relation['targetAlias'])
        self.assertTrue(set(fact['subjectAliases']+[relation['sourceAlias'],relation['targetAlias']]).issubset(aliases))
    def test_candidate_ranking_does_not_treat_null_names_as_matches(self):
        for i in range(5): self.s.add_item(kind='fact',subtype='trait',content=f'unrelated {i}')
        target=self.s.add_item(kind='fact',subtype='trait',content='needle memory')
        candidates,aliases=self.s.build_stage_b_candidates(None,[{'content':'needle memory'}],limit=5)
        self.assertIn(target,aliases.values())
        self.assertTrue(any(item['content']=='needle memory' for item in candidates))
    def test_candidate_ranking_keeps_newest_exact_content_over_partial_overlap(self):
        for i in range(6): self.s.add_item(kind='fact',subtype='trait',content=f'exact profile filler {i}')
        target=self.s.add_item(kind='entity',subtype='person',name='Ada',content='exact profile')
        candidates,aliases=self.s.build_stage_b_candidates(None,[{'kind':'entity','name':'Ada','content':' exact   profile '}],limit=5)
        self.assertIn(target,aliases.values())
        self.assertTrue(any(item['alias']==next(alias for alias,mid in aliases.items() if mid==target) for item in candidates))
        self.assertLessEqual(sum(item['kind'] != 'entity' or item['content'] != 'exact profile' for item in candidates),4)
    def test_candidate_closure_covers_six_exact_items_beyond_primary_limit(self):
        ids=[self.s.add_item(kind='entity',subtype='person',name=f'Person{i}',content=f'profile {i}') for i in range(6)]
        extracted=[{'turnNumber':1,'kind':'entity','subtype':'person','name':f'Person{i}','content':f'profile {i}'} for i in range(6)]
        candidates,aliases=self.s.build_stage_b_candidates(None,extracted,limit=5)
        self.assertTrue(set(ids).issubset(set(aliases.values())))
        self.assertGreaterEqual(len(candidates),6)
        before=len(self.s.active_rows(None))
        by_id={mid:alias for alias,mid in aliases.items()}
        operations=[{'op':'NOOP','sourceItemIndex':i,'sourceTurnNumber':1,'alias':by_id[mid]} for i,mid in enumerate(ids)]
        self.s.apply_operations(None,operations,aliases)
        self.assertEqual(len(self.s.active_rows(None)),before)
    def test_candidate_closure_relation_identity_keeps_direction(self):
        ada=self.s.add_item(kind='entity',subtype='person',name='Ada',content='ada')
        bob=self.s.add_item(kind='entity',subtype='person',name='Bob',content='bob')
        correct=self.s.add_item(kind='relation',subtype='friend',content='friends',source_id=ada,target_id=bob)
        self.s.add_item(kind='relation',subtype='friend',content='friends',source_id=bob,target_id=ada)
        extracted=[{'turnNumber':1,'kind':'relation','subtype':'friend','sourceName':'Ada','targetName':'Bob','content':'friends'}]
        _candidates,aliases=self.s.build_stage_b_candidates(None,extracted,limit=1)
        self.assertIn(correct,aliases.values())
        before=len(self.s.active_rows(None))
        alias=next(key for key,value in aliases.items() if value==correct)
        self.s.apply_operations(None,[{'op':'NOOP','sourceItemIndex':0,'sourceTurnNumber':1,'alias':alias}],aliases)
        self.assertEqual(len(self.s.active_rows(None)),before)
    def test_candidate_closure_fact_identity_includes_subjects_and_six_relations(self):
        people=[self.s.add_item(kind='entity',subtype='person',name=f'P{i}',content=f'p{i}') for i in range(7)]
        correct_fact=self.s.add_item(kind='fact',subtype='trait',content='brave',subject_ids=[people[0]])
        self.s.add_item(kind='fact',subtype='trait',content='brave',subject_ids=[people[1]])
        relations=[self.s.add_item(kind='relation',subtype='friend',content=f'link {i}',source_id=people[i],target_id=people[i+1]) for i in range(6)]
        extracted=[{'turnNumber':1,'kind':'fact','subtype':'trait','subjectNames':['P0'],'content':'brave','turnRange':[1,1]}]
        extracted += [{'turnNumber':1,'kind':'relation','subtype':'friend','sourceName':f'P{i}','targetName':f'P{i+1}','content':f'link {i}'} for i in range(6)]
        candidates,aliases=self.s.build_stage_b_candidates(None,extracted,limit=5)
        self.assertIn(correct_fact,aliases.values())
        self.assertTrue(set(relations).issubset(aliases.values()))
        self.assertTrue(all(item['kind']=='entity' or item['kind']!='relation' or (item['sourceAlias'] and item['targetAlias']) for item in candidates))
        before=len(self.s.active_rows(None)); reverse={value:key for key,value in aliases.items()}
        operations=[{'op':'NOOP','sourceItemIndex':0,'sourceTurnNumber':1,'alias':reverse[correct_fact]}]
        operations += [{'op':'NOOP','sourceItemIndex':index+1,'sourceTurnNumber':1,'alias':reverse[mid]} for index,mid in enumerate(relations)]
        self.s.apply_operations(None,operations,aliases)
        self.assertEqual(len(self.s.active_rows(None)),before)
    def test_candidate_subject_precompute_is_scoped_not_global_scan(self):
        target_person=self.s.add_item(kind='entity',subtype='person',name='Target',content='target',session_id='target')
        self.s.add_item(kind='fact',subtype='trait',content='needle',subject_ids=[target_person],session_id='target')
        other_person=self.s.add_item(kind='entity',subtype='person',name='Other',content='other',session_id='other')
        for index in range(500): self.s.add_item(kind='fact',subtype='trait',content=f'noise {index}',subject_ids=[other_person],session_id='other')
        queries=[]; original=self.s._connect
        def traced_connect():
            connection=original(); connection.set_trace_callback(queries.append); return connection
        self.s._connect=traced_connect
        try:
            self.s.build_stage_b_candidates('target',[{'kind':'fact','subtype':'trait','subjectNames':['Target'],'content':'needle'}])
        finally:
            self.s._connect=original
        subject_queries=[query.upper() for query in queries if 'SELECT FACT_ID,ENTITY_ID FROM FACT_SUBJECT' in query.upper()]
        self.assertTrue(subject_queries)
        self.assertTrue(all(' WHERE FACT_ID IN ' in query for query in subject_queries))
    def test_session_operations_cannot_mutate_global_canon(self):
        global_id=self.s.add_item(kind='entity',subtype='person',name='Canon',content='global')
        op={'op':'UPDATE_ENTITY','sourceTurnNumber':1,'alias':'e0','subtype':'person','name':'Canon','content':'changed','turnRange':None,'reason':None}
        with self.assertRaises(ValueError): self.s.apply_operations('room',[op],{'e0':global_id})
        self.assertEqual(self.s.active_rows(None,'entity')[0]['content'],'global')
        mapping=self.s.canon_snapshot('room')
        self.s.apply_operations('room',[op],{'e0':mapping[global_id]})
        self.assertEqual(self.s.active_rows(None,'entity')[0]['content'],'global')
        self.assertEqual(self.s.active_rows('room','entity')[0]['content'],'changed')
    def test_supersede_inserts_replacement_and_links_history(self):
        old=self.s.add_item(kind='entity',subtype='person',name='Ada',content='old',session_id='room')
        op={'op':'SUPERSEDE_ENTITY','sourceTurnNumber':2,'alias':'e0','subtype':'person','name':'Ada','content':'new','turnRange':[2,2],'reason':'identity changed'}
        aliases=self.s.apply_operations('room',[op],{'e0':old})
        active=self.s.active_rows('room','entity')
        self.assertEqual(len(active),1)
        self.assertEqual(active[0]['content'],'new')
        self.assertEqual(aliases['e0'],active[0]['id'])
        with self.s._session() as connection:
            history=connection.execute('SELECT status,superseded_by FROM memory WHERE id=?',(old,)).fetchone()
        self.assertEqual(history['status'],'superseded')
        self.assertEqual(history['superseded_by'],active[0]['id'])
    def test_supersede_entity_rewires_active_graph_references(self):
        old=self.s.add_item(kind='entity',subtype='person',name='Ada',content='old',session_id='room')
        bob=self.s.add_item(kind='entity',subtype='person',name='Bob',content='bob',session_id='room')
        fact=self.s.add_item(kind='fact',subtype='trait',content='likes stars',session_id='room',subject_ids=[old])
        relation=self.s.add_item(kind='relation',subtype='friend',content='friends',session_id='room',source_id=old,target_id=bob)
        heard=self.s.add_item(kind='fact',subtype='moment',content='heard it',session_id='room')
        with self.s._session() as connection:
            connection.execute('UPDATE memory SET heard_from=? WHERE id=?',(old,heard))
        op={'op':'SUPERSEDE_ENTITY','sourceTurnNumber':2,'alias':'e0','subtype':'person','name':'Ada','content':'new','turnRange':[2,2],'reason':'identity changed'}
        new_id=self.s.apply_operations('room',[op],{'e0':old})['e0']
        with self.s._session() as connection:
            subject=connection.execute('SELECT entity_id FROM fact_subject WHERE fact_id=?',(fact,)).fetchone()[0]
            edge=connection.execute('SELECT source_id FROM memory WHERE id=?',(relation,)).fetchone()[0]
            source=connection.execute('SELECT heard_from FROM memory WHERE id=?',(heard,)).fetchone()[0]
        self.assertEqual((subject,edge,source),(new_id,new_id,new_id))
    def test_snapshot_and_context(self):
        a=self.s.add_item(kind='entity',subtype='person',name='A',content='a'); f=self.s.add_item(kind='fact',subtype='trait',content='kind',subject_ids=[a]); mp=self.s.canon_snapshot('z'); self.assertIn(a,mp); self.assertEqual(len(self.s.active_rows('z','fact')),1)
        msgs=[{'id':i,'role':'user','content':str(i)} for i in range(70)]; c=assemble_context('intro','static',msgs,0,'mem'); self.assertEqual(len(c),63); self.assertEqual(c[2]['id'],10); self.assertEqual(c[-2]['content'],'mem'); self.assertEqual(c[-1]['id'],69)
    def test_retrieval_cache_and_names(self):
        self.s.add_item(kind='entity',subtype='person',name='Ann',content='Ann'); self.s.add_item(kind='fact',subtype='trait',content='brave',subject_ids=[1]); r=self.s.retrieve(None,'Tell me about Ann?'); self.assertTrue(r.gate); self.assertLessEqual(r.counts['traits'],8); n=self.e.calls; self.s.retrieve(None,'Tell me about Ann?'); self.assertEqual(n,self.e.calls)
        self.s.retrieve(None,'Tell me about Ann?',current_turn=9); self.assertEqual(n,self.e.calls)
        self.assertTrue(self.s.retrieve(None,'Ann says hi').gate)
        self.assertEqual(NameScanner().scan('Annabelle Ann',['Ann','Annabelle']),['Annabelle','Ann'])
        self.assertEqual(NameScanner().scan('tell me about ann',['Ann']),['Ann'])

    def test_journal_recall_is_bounded_complete_and_session_scoped(self):
        for turn in range(1, 7):
            self.s.append_turn('s', f'user {turn}', f'assistant secret{turn}', turn)
        self.s.append_turn('other', 'secret other', 'answer other', 1)
        self.s.append_message('s', 7, 'user', 'secret incomplete')
        rows = self.s.unextracted_messages('s')
        self.s.extraction_success('s', [rows[2]['id'], rows[3]['id']], 2)
        before = self.s.job_state_readonly('s')
        recalled = self.s.journal_recall('s', 'SECRET1 secret3 secret7', retained_turns=[1])
        self.assertEqual([message['content'] for message in recalled], ['user 3', 'assistant secret3'])
        self.assertEqual(self.s.job_state_readonly('s'), before)

    def test_journal_recall_caps_and_cache_invalidation_state(self):
        for turn in range(1, 8):
            self.s.append_turn('s', 'u' * 250, f'needle {turn}' + 'a' * 100, turn)
        recalled = self.s.journal_recall('s', 'needle', ())
        self.assertLessEqual(len(recalled), 8)
        self.assertLessEqual(sum(len(message['content']) for message in recalled), 1200)
        self.assertEqual(self.s.journal_recall('s', 'absent', ()), [])
        first = self.s.retrieve('s', 'tell me needle', journal_retained_turns=[7])
        self.s.append_turn('s', 'new needle', 'new answer', 8)
        second = self.s.retrieve('s', 'tell me needle', journal_retained_turns=[8])
        self.assertNotEqual(first.journal_messages, second.journal_messages)
        rows = self.s.unextracted_messages('s')
        self.s.extraction_success('s', [row['id'] for row in rows[-4:-2]], 7)
        third = self.s.retrieve('s', 'tell me needle', journal_retained_turns=[8])
        self.assertNotEqual(second.journal_messages, third.journal_messages)

    def test_short_lexical_questions_recall_pending_journal_without_active_gate(self):
        self.s.append_turn('room', 'vault code 암호 is cobalt-47', 'I will remember cobalt-47.', 1)
        before = self.s.job_state_readonly('room')
        english = self.s.retrieve('room', 'the code?', journal_retained_turns=())
        korean = self.s.retrieve('room', '암호 알려줘', journal_retained_turns=())
        self.assertFalse(english.gate)
        self.assertIn('cobalt-47', " ".join(message['content'] for message in english.journal_messages))
        self.assertIn('vault code 암호 is cobalt-47', [message['content'] for message in korean.journal_messages])
        self.assertEqual(self.s.retrieve('room', 'hello', journal_retained_turns=()).journal_messages, [])
        self.assertEqual(self.s.retrieve('other', 'the code?', journal_retained_turns=()).journal_messages, [])
        self.assertEqual(self.s.job_state_readonly('room'), before)

    def test_korean_particle_variants_recall_the_same_noun(self):
        self.s.append_turn('room', '\uc81c \ubcc4\uba85\uc740 \ubc18\uc9dd\uc774\uc57c', '\uae30\uc5b5\ud574\ub458\uac8c', 1)
        recalled = self.s.retrieve('room', '\ub0b4 \ubcc4\uba85 \uae30\uc5b5\ub098?', journal_retained_turns=())
        self.assertIn('\uc81c \ubcc4\uba85\uc740 \ubc18\uc9dd\uc774\uc57c', [message['content'] for message in recalled.journal_messages])

    def test_journal_recall_window_is_4096_messages(self):
        for turn in range(1, 2051):
            marker = 'outside-window' if turn == 1 else ('inside-window' if turn == 2050 else 'filler')
            self.s.append_turn('s', f'code {marker}', f'answer {marker}', turn)
        recalled = self.s.journal_recall('s', 'code', ())
        contents = [message['content'] for message in recalled]
        self.assertIn('code inside-window', contents)
        self.assertNotIn('code outside-window', contents)

    def test_journal_recall_uses_fts_candidates_and_keeps_korean_stem_aliases(self):
        self.s.append_turn('s', '제 별명은 반짝이야', '기억해둘게', 1)
        queries = []
        original_connect = self.s._connect
        def traced_connect():
            connection = original_connect(); connection.set_trace_callback(queries.append); return connection
        self.s._connect = traced_connect
        try:
            recalled = self.s.journal_recall('s', '별명 기억나?', ())
        finally:
            self.s._connect = original_connect
        self.assertIn('제 별명은 반짝이야', [message['content'] for message in recalled])
        self.assertTrue(any('CONVERSATION_MESSAGE_FTS MATCH' in query.upper() for query in queries))

    def test_retention_bounds_session_journal_and_memory_without_base_deletion(self):
        self.s.add_item(kind='entity', subtype='person', name='base', content='base', source='base')
        with self.s._session() as c:
            c.executemany("INSERT INTO conversation_message(session_id,turn_no,role,content,content_hash,recall_chars) VALUES (?,?,?,?,?,?)",
                [('room', index, 'user', 'u', str(index), 1) for index in range(1, 4101)])
            c.execute("INSERT INTO session_activity(session_id,latest_message_id,latest_turn) "
                      "SELECT 'room',MAX(id),MAX(turn_no) FROM conversation_message WHERE session_id='room'")
            c.executemany("INSERT INTO memory(session_id,source,kind,subtype,name,content) VALUES (?,?,?,?,?,?)",
                [('room', 'conversation', 'entity', 'person', f'n{index}', 'x') for index in range(2050)])
        result = self.s.run_retention(force=True)
        with self.s._session() as c:
            messages = c.execute("SELECT COUNT(*) FROM conversation_message WHERE session_id='room'").fetchone()[0]
            memories = c.execute("SELECT COUNT(*) FROM memory WHERE session_id='room'").fetchone()[0]
            base = c.execute("SELECT COUNT(*) FROM memory WHERE session_id IS NULL").fetchone()[0]
        self.assertTrue(result['ran'])
        self.assertEqual((messages, memories, base), (4096, 2048, 1))

    def test_journal_recall_does_not_tokenize_overlong_recent_window_pairs(self):
        overlong = "needle " + ("x" * 16384)
        rows = []
        for turn in range(1, 2049):
            rows.extend((("s", turn, "user", overlong, "user", 1201),
                         ("s", turn, "assistant", overlong, "assistant", 1201)))
        with self.s._session() as connection:
            connection.executemany(
                "INSERT INTO conversation_message(session_id,turn_no,role,content,content_hash,recall_chars) VALUES (?,?,?,?,?,?)",
                rows,
            )
        original = self.s._journal_tokens
        tokenized = []
        self.s._journal_tokens = lambda text: (tokenized.append(text), original(text))[1]
        original_connect = self.s._connect
        queries = []
        def traced_connect():
            connection = original_connect()
            connection.set_trace_callback(queries.append)
            return connection
        self.s._connect = traced_connect
        try:
            self.assertEqual(self.s.journal_recall("s", "needle", ()), [])
            self.assertTrue(all(len(text) <= 1200 for text in tokenized))
        finally:
            self.s._journal_tokens = original
            self.s._connect = original_connect
        self.assertFalse(any("LENGTH(MESSAGE.CONTENT)" in query.upper() for query in queries))
        self.assertTrue(any("INDEXED BY IX_CONVERSATION_RECALL_META" in query.upper() for query in queries))
        self.s.append_turn("s", "needle normal", "normal answer", 2049)
        recalled = self.s.journal_recall("s", "needle", ())
        self.assertEqual([message["content"] for message in recalled], ["needle normal", "normal answer"])

    def test_recall_metadata_migration_leaves_legacy_text_unscanned_and_adds_new_rows(self):
        legacy_db = self.db + ".legacy"
        connection = sqlite3.connect(legacy_db)
        connection.execute("CREATE TABLE conversation_message (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, turn_no INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL, extracted INTEGER NOT NULL DEFAULT 0, UNIQUE(session_id,turn_no,role))")
        connection.execute("INSERT INTO conversation_message(session_id,turn_no,role,content,content_hash) VALUES ('s',1,'user','legacy code','u')")
        connection.execute("INSERT INTO conversation_message(session_id,turn_no,role,content,content_hash) VALUES ('s',1,'assistant','legacy answer','a')")
        connection.commit(); connection.close()
        store = MemoryStore(legacy_db)
        try:
            with store._session() as migrated:
                columns = {row[1] for row in migrated.execute("PRAGMA table_info(conversation_message)")}
                legacy_chars = [row[0] for row in migrated.execute("SELECT recall_chars FROM conversation_message WHERE turn_no=1")]
            self.assertIn("recall_chars", columns)
            self.assertEqual(legacy_chars, [None, None])
            self.assertEqual(store.journal_recall("s", "code", ()), [])
            store.append_turn("s", "new code", "new answer", 2)
            self.assertEqual([message["content"] for message in store.journal_recall("s", "code", ())], ["new code", "new answer"])
        finally:
            os.unlink(legacy_db)

    def test_bootstrap_is_bounded_and_preserves_incoming_ordinals(self):
        turns = [(turn, f'u{turn}', f'a{turn}') for turn in range(1, 1001)]
        self.assertEqual(self.s.bootstrap_turns_if_empty('new', turns), 60)
        rows = self.s.unextracted_messages('new')
        self.assertEqual(len(rows), 120)
        self.assertEqual((rows[0]['turn_no'], rows[-1]['turn_no']), (941, 1000))
        self.assertEqual(self.s.bootstrap_turns_if_empty('new', turns), 0)

    def test_user_tail_requires_complete_unique_candidate(self):
        users = ['one', 'two', 'three', 'four']
        for sid in ('a', 'b'):
            for turn, user in enumerate(users, 1): self.s.append_turn(sid, user, 'canonical', turn)
        hashes = [__import__('hashlib').sha256(user.encode()).hexdigest() for user in users]
        self.assertIsNone(self.s.find_session_by_user_tail(hashes, min_turns=4, min_distinct=3))
        self.s.append_message('incomplete', 1, 'user', 'one')
        self.assertEqual(self.s.recent_completed_user_hashes('incomplete'), [])

    def test_session_activity_backfill_and_write_order(self):
        self.s.append_turn('older', 'u1', 'a1', 1)
        self.s.append_message('newer', 9, 'user', 'u9')
        with self.s._session() as connection:
            activity = connection.execute('SELECT session_id,latest_message_id,latest_turn FROM session_activity ORDER BY latest_message_id').fetchall()
        self.assertEqual([row['session_id'] for row in activity], ['older', 'newer'])
        self.assertEqual(activity[-1]['latest_turn'], 9)

    def test_exact_tail_matcher_is_bounded_at_256_sessions_by_60_turns(self):
        turns = [(turn, f'user-{turn}', f'assistant-{turn}') for turn in range(1, 61)]
        for index in range(256): self.s.bootstrap_turns_if_empty(f'session-{index}', turns)
        started = __import__('time').perf_counter()
        self.assertIsNone(self.s.find_session_by_turn_tail([('x', 'y'), ('z', 'q')]))
        self.assertLess(__import__('time').perf_counter() - started, .15)

    def test_completed_turn_tail_caps_and_append_message_completion(self):
        for turn in range(1, 66): self.s.append_turn('tail', f'u{turn}', f'a{turn}', turn)
        with self.s._session() as connection:
            turns = [row[0] for row in connection.execute('SELECT turn_no FROM session_turn_tail WHERE session_id=? ORDER BY turn_no', ('tail',))]
        self.assertEqual((len(turns), turns[0], turns[-1]), (60, 6, 65))
        self.s.append_message('split', 1, 'user', 'u')
        self.assertEqual(self.s.recent_turn_hashes('split'), [])
        self.s.append_message('split', 1, 'assistant', 'a')
        self.assertEqual(len(self.s.recent_turn_hashes('split')), 1)

    def test_turn_tail_backfills_existing_journal_on_reopen(self):
        self.s.append_turn('legacy', 'u', 'a', 1)
        with self.s._session() as connection: connection.execute('DELETE FROM session_turn_tail')
        reopened = MemoryStore(self.db)
        self.assertEqual(len(reopened.recent_turn_hashes('legacy')), 1)
    def test_cache_disabled_disables_result_and_query_caches(self):
        self.s.cache_enabled=False
        self.s.add_item(kind='entity',subtype='person',name='Ada',content='Ada')
        before=self.e.calls
        self.s.retrieve(None,'tell me about ada',current_turn=1)
        self.s.retrieve(None,'tell me about ada',current_turn=2)
        self.assertEqual(self.e.calls-before,2)
        self.assertEqual((self.s._cache,self.s._query_cache),({},{}))

    def test_static_semantic_cache_and_dynamic_scope_bypass(self):
        entity = self.s.add_item(kind='entity', subtype='person', name='Ada', content='Ada', source='base')
        self.s.add_item(kind='fact', subtype='trait', content='Ada is brave', source='base', subject_ids=[entity])
        self.s.retrieve(None, 'tell me about Ada first')
        self.assertEqual(len(self.s._semantic_cache), 1)
        self.s.retrieve(None, 'tell me about Ada second')
        self.assertEqual(len(self.s._semantic_cache), 1)
        self.s.add_item(kind='fact', subtype='moment', content='dynamic', subject_ids=[entity], turn_range=(1, 1))
        self.s._semantic_cache.clear(); self.s._context_cache.clear()
        self.s.retrieve(None, 'tell me about Ada third')
        self.assertEqual((self.s._semantic_cache, self.s._context_cache), ({}, {}))

    def test_semantic_cache_version_and_environment_off_clear_all_caches(self):
        entity = self.s.add_item(kind='entity', subtype='person', name='Ada', content='Ada', source='base')
        self.s.add_item(kind='fact', subtype='trait', content='Ada is brave', source='base', subject_ids=[entity])
        self.s.retrieve(None, 'tell me about Ada one')
        old_keys = set(self.s._semantic_cache)
        self.s.add_item(kind='fact', subtype='trait', content='Ada is kind', source='base', subject_ids=[entity])
        self.s.retrieve(None, 'tell me about Ada two')
        self.assertNotEqual(old_keys, set(self.s._semantic_cache))
        with patch.dict(os.environ, {'RAG_CACHE':'off'}):
            self.s.retrieve(None, 'tell me about Ada three')
        self.assertEqual((self.s._cache, self.s._query_cache, self.s._semantic_cache, self.s._context_cache), ({}, {}, {}, {}))

    def test_semantic_near_hit_dissimilar_miss_and_context_qvec_guard(self):
        class V:
            def __init__(self): self.calls=[]
            def encode(self, texts):
                self.calls.extend(texts)
                return [[1., 0.] if 'near-one' in text else ([.99, .1] if 'near-two' in text else [0., 1.]) for text in texts]
        v=V(); self.s.embedder=v
        entity=self.s.add_item(kind='entity',subtype='person',name='Ada',content='Ada',source='base')
        self.s.add_item(kind='fact',subtype='trait',content='Ada brave',source='base',subject_ids=[entity])
        v.calls.clear()
        self.assertFalse(self.s.retrieve(None,'tell Ada near-one').cache_hit)
        self.assertTrue(self.s.retrieve(None,'tell Ada near-two').cache_hit)
        self.assertFalse(self.s.retrieve(None,'tell Ada far').cache_hit)
        self.assertEqual(len(self.s._semantic_cache),2)
        self.assertEqual(self.s._context_cache,{})  # vectors never use top-1 context reuse
        self.s.embedder=None
        self.assertFalse(self.s.retrieve(None,'tell Ada lexical-one').cache_hit)
        self.assertTrue(self.s.retrieve(None,'tell Ada lexical-two').cache_hit)
        self.assertTrue(self.s._context_cache)

    def test_semantic_filter_isolation_and_journal_recall_is_not_cached(self):
        class V:
            def encode(self, texts): return [[1.,0.] for _ in texts]
        self.s.embedder=V()
        entity=self.s.add_item(kind='entity',subtype='person',name='Ada',content='Ada',source='base')
        self.s.add_item(kind='fact',subtype='trait',content='Ada brave',source='base',subject_ids=[entity])
        self.s.append_turn('room','old alpha','answer alpha',1); self.s.append_turn('room','old beta','answer beta',2)
        first=self.s.retrieve('room','tell Ada alpha one',attendees=('x',),journal_retained_turns=(99,))
        second=self.s.retrieve('room','tell Ada beta two',attendees=('x',),journal_retained_turns=(99,))
        self.assertTrue(second.cache_hit)
        self.assertNotEqual(first.journal_messages,second.journal_messages)
        self.s.retrieve('room','tell Ada beta three',attendees=('y',),journal_retained_turns=(99,))
        self.s.retrieve('other','tell Ada beta four',attendees=('x',),journal_retained_turns=(99,))
        self.assertGreaterEqual(len(self.s._semantic_cache),3)
        self.assertTrue(all(len(value)==4 and isinstance(value[2],str) and isinstance(value[3],dict)
                            for value in self.s._semantic_cache.values()))

    def test_cache_ttl_cap_and_disabled_clear_all_layers(self):
        for index in range(513): self.s._cache_put(self.s._semantic_cache, (0, index, str(index)), (0., [1.], '', {}))
        self.assertEqual(len(self.s._semantic_cache),512)
        self.s._semantic_cache.clear()
        self.s._semantic_cache[('old',)] = (0., [1.], '', {})
        with patch('airi_memory.time.monotonic', return_value=601.):
            self.s.retrieve(None,'tell me something long enough')
        self.assertNotIn(('old',),self.s._semantic_cache)
        self.s._cache[('x',)]=(1.,None); self.s._query_cache[('x',)]=(1.,[1.]); self.s._context_cache[('x',)]=(1.,'',{})
        self.s.cache_enabled=False
        self.s.retrieve(None,'tell me something long enough')
        self.assertEqual((self.s._cache,self.s._query_cache,self.s._semantic_cache,self.s._context_cache),({},{},{},{}))

    def test_concurrent_retrieval_cache_access_is_bounded(self):
        entity=self.s.add_item(kind='entity',subtype='person',name='Ada',content='Ada',source='base')
        self.s.add_item(kind='fact',subtype='trait',content='Ada brave',source='base',subject_ids=[entity])
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda index:self.s.retrieve(None,f'tell Ada request {index}'), range(32)))
        self.assertTrue(all(result.gate for result in results))
        self.assertLessEqual(max(len(self.s._cache),len(self.s._query_cache),len(self.s._semantic_cache),len(self.s._context_cache)),512)

    def test_exact_cache_is_detached_from_caller_mutation(self):
        entity=self.s.add_item(kind='entity',subtype='person',name='Ada',content='Ada')
        self.s.add_item(kind='fact',subtype='trait',content='Ada brave',subject_ids=[entity])
        first=self.s.retrieve(None,'tell me about Ada')
        pristine=(first.block,dict(first.counts),list(first.journal_messages))
        first.block='poison'; first.counts['entities']=999; first.journal_messages.append({'role':'assistant','content':'poison'})
        second=self.s.retrieve(None,'tell me about Ada')
        self.assertEqual((second.block,second.counts,second.journal_messages),pristine)

    def test_disabled_cache_clears_all_layers_before_short_gate(self):
        for cache, value in ((self.s._cache,(1.,None)), (self.s._query_cache,(1.,[1.])),
                             (self.s._semantic_cache,(1.,[1.],'',{})), (self.s._context_cache,(1.,'',{}))):
            cache[('seed',)]=value
        with patch.dict(os.environ, {'RAG_CACHE':'off'}): self.s.retrieve(None,'hi')
        self.assertEqual((self.s._cache,self.s._query_cache,self.s._semantic_cache,self.s._context_cache),({},{},{},{}))
        self.s._cache[('seed',)]=(1.,None); self.s.cache_enabled=False
        self.s.retrieve(None,'hi')
        self.assertEqual((self.s._cache,self.s._query_cache,self.s._semantic_cache,self.s._context_cache),({},{},{},{}))
    def test_no_embedder_first_person_question_uses_user_entity(self):
        self.s.embedder=None
        user=self.s.add_item(kind='entity',subtype='person',name='{{user}}',content='the user')
        self.s.add_item(kind='fact',subtype='trait',content='likes stargazing',subject_ids=[user])
        result=self.s.retrieve(None,'What do I like?')
        self.assertIn('likes stargazing',result.block)
    def test_relation_one_hop_facts_are_retrieved_without_semantic_entity_expansion(self):
        self.s.embedder=None
        a=self.s.add_item(kind='entity',subtype='person',name='Ada',content='Ada')
        b=self.s.add_item(kind='entity',subtype='person',name='Bob',content='Bob')
        self.s.add_item(kind='relation',subtype='friend',content='Ada and Bob are friends',source_id=a,target_id=b)
        self.s.add_item(kind='fact',subtype='trait',content='Ada likes tea',subject_ids=[a])
        self.s.add_item(kind='fact',subtype='trait',content='Bob keeps the observatory key',subject_ids=[b])
        result=self.s.retrieve(None,'Tell me about Ada?')
        self.assertEqual(result.counts['entities'],1)
        self.assertEqual(result.counts['relations'],1)
        self.assertEqual(result.counts['one_hop_facts'],1)
        self.assertIn('Bob keeps the observatory key',result.block)
    def test_scene_overfetch_uses_vector_relevance_before_final_rerank(self):
        for i in range(20):
            self.s.add_item(kind='fact',subtype='scene',content=f'noise scene {i}',turn_range=(i+2,i+2),vector=pack_vector([0.,1.]))
        self.s.add_item(kind='fact',subtype='scene',content='exact scene',turn_range=(1,1),vector=pack_vector([1.,0.]))
        result=self.s.retrieve(None,'Tell me every relevant detail about this scene')
        self.assertIn('exact scene',result.block)
    def test_job_failure_keeps_watermark(self):
        self.s.job_success('x',4); self.s.job_failure('x'); self.assertEqual(self.s.job_state('x')['extracted_up_to_msg'],4)
    def test_journal_isolated_and_success(self):
        one=self.s.append_message('one',1,'user','private'); two=self.s.append_message('two',1,'assistant','other')
        self.s.extraction_success('one',[one],one)
        self.assertEqual(len(self.s.unextracted_messages('one')),0)
        self.assertEqual(len(self.s.unextracted_messages('two')),1)
        before=self.s.job_state('two')['extracted_up_to_msg']; self.s.job_failure('two'); self.assertEqual(before,self.s.job_state('two')['extracted_up_to_msg'])
    def test_extraction_success_preserves_messages_arriving_during_extraction(self):
        first=self.s.append_message('s',1,'user','first')
        self.s.append_message('s',2,'user','arrived later')
        self.s.extraction_success('s',[first],1)
        state=self.s.job_state('s')
        self.assertEqual(state['pending_msgs'],1)
        self.assertEqual([row['content'] for row in self.s.unextracted_messages('s')],['arrived later'])
    def test_snapshot_idempotent_and_no_reembed(self):
        a=self.s.add_item(kind='entity',subtype='person',name='Canon',content='canon')
        calls=self.e.calls; first=self.s.canon_snapshot('room'); second=self.s.canon_snapshot('room')
        self.assertEqual(first,second); self.assertEqual(calls,self.e.calls)
        self.assertEqual(len([x for x in self.s.active_rows('room') if x['name']=='Canon']),1)
    def test_empty_snapshot_does_not_absorb_later_global_canon(self):
        self.assertEqual(self.s.canon_snapshot('empty-room'),{})
        self.s.add_item(kind='entity',subtype='person',name='Later',content='later canon')
        self.assertEqual(self.s.active_rows('empty-room'),[])
    def test_journal_retransmission_idempotent(self):
        a=self.s.append_message('s',1,'user','same'); b=self.s.append_message('s',1,'user','same')
        self.assertEqual(a,b); self.assertEqual(self.s.job_state('s')['pending_msgs'],1)
        with self.assertRaises(ValueError): self.s.append_message('s',1,'user','changed')
    def test_completed_turn_append_is_atomic_and_monotonic(self):
        first=self.s.append_turn('s','u1','a1',1)
        second=self.s.append_turn('s','u2','a2',1)
        self.assertEqual((first[0],second[0]),(1,2))
        self.assertEqual(self.s.job_state('s')['pending_msgs'],4)
        with self.assertRaises(ValueError): self.s.append_turn('s','u3','',1)
        self.assertEqual(self.s.latest_turn('s'),2)
    def test_explicit_tail_adopts_bounded_history_and_is_idempotent(self):
        turns=[(n,f'u{n}',f'a{n}') for n in range(1,1001)]
        self.assertEqual(self.s.adopt_explicit_turn_tail('header',turns),60)
        self.assertEqual(self.s.latest_turn('header'),1000)
        self.assertEqual(len(self.s.unextracted_messages('header')),120)
        self.assertEqual(self.s.adopt_explicit_turn_tail('header',turns),0)
        self.assertEqual(self.s.job_state('header')['pending_msgs'],120)
    def test_explicit_tail_backfills_prefix_and_rejects_conflict(self):
        self.s.append_turn('header','u59','a59',599); self.s.append_turn('header','u60','a60',600)
        turns=[(n,f'u{n-540}',f'a{n-540}') for n in range(541,601)]
        self.assertEqual(self.s.adopt_explicit_turn_tail('header',turns),58)
        self.assertEqual(self.s.latest_turn('header'),600)
        before=self.s.job_state('header')['pending_msgs']
        bad=turns[:-1]+[(600,'different-user','a60')]
        with self.assertRaises(ValueError): self.s.adopt_explicit_turn_tail('header',bad)
        self.assertEqual(self.s.job_state('header')['pending_msgs'],before)
    def test_explicit_tail_rejects_nonempty_target_without_overlap(self):
        self.s.append_turn('header','old-user','old-answer',100)
        before=self.s.job_state('header')['pending_msgs']
        with self.assertRaises(ValueError):
            self.s.adopt_explicit_turn_tail('header',[(599,'new-user','new-answer')])
        self.assertEqual(self.s.latest_turn('header'),100)
        self.assertEqual(self.s.job_state('header')['pending_msgs'],before)
    def test_explicit_tail_uses_two_distinct_user_anchors_for_wire_assistant_mismatch(self):
        self.s.append_turn('header','u59','canonical-a59',599)
        self.s.append_turn('header','u60','canonical-a60',600)
        turns=[(n,f'u{n-540}',f'a{n-540}') for n in range(541,599)]
        turns.extend([(599,'u59','wire-framed-a59'),(600,'u60','wire-framed-a60')])
        self.assertEqual(self.s.adopt_explicit_turn_tail('header',turns),58)
        self.assertEqual(self.s.latest_turn('header'),600)
        self.assertEqual(len(self.s.unextracted_messages('header')),120)
    def test_explicit_tail_rejects_wire_mismatch_without_two_distinct_user_anchors(self):
        self.s.append_turn('header','same','canonical',599)
        self.s.append_turn('header','same','canonical',600)
        before=self.s.job_state('header')['pending_msgs']
        with self.assertRaises(ValueError):
            self.s.adopt_explicit_turn_tail(
                'header',[(599,'same','wire-a'),(600,'same','wire-b')]
            )
        self.assertEqual(self.s.job_state('header')['pending_msgs'],before)
    def test_explicit_tail_normalizes_leading_act_envelope_only(self):
        turns=[(1,'u','<|ACT {"emotion":"neutral"}| answer')]
        self.assertEqual(self.s.adopt_explicit_turn_tail('header',turns),1)
        self.assertEqual(self.s.adopt_explicit_turn_tail('header',[(1,'u','answer')]),0)
    def test_journal_recall_never_reinjects_leading_act_envelope(self):
        self.s.append_turn('header','vault code is cobalt-47',
                           '<|ACT {"emotion":"neutral"}|> remembered cobalt-47',1)
        recalled=self.s.journal_recall('header','what is the cobalt-47 code?',[])
        self.assertEqual(recalled[-1]['content'],'remembered cobalt-47')
        self.assertFalse(any('<|ACT' in item['content'] for item in recalled))
    def test_find_session_by_turn_tail_recovers_exact_completed_history(self):
        self.s.append_turn('known','u1','a1')
        self.s.append_turn('known','u2','a2')
        incoming=self.s.recent_turn_hashes('known')
        self.assertEqual(self.s.find_session_by_turn_tail(incoming),'known')
    def test_find_session_by_turn_tail_allows_truncated_client_history(self):
        for i in range(4): self.s.append_turn('known',f'u{i}',f'a{i}')
        incoming=self.s.recent_turn_hashes('known')[-2:]
        self.assertEqual(self.s.find_session_by_turn_tail(incoming),'known')
    def test_find_session_by_turn_tail_never_recovers_on_one_turn(self):
        self.s.append_turn('known','hello','hi')
        self.assertIsNone(self.s.find_session_by_turn_tail(self.s.recent_turn_hashes('known')))
    def test_find_session_by_turn_tail_returns_none_for_no_or_ambiguous_match(self):
        self.s.append_turn('one','u1','a1'); self.s.append_turn('one','u2','a2')
        self.s.append_turn('two','u1','a1'); self.s.append_turn('two','u2','a2')
        tail=self.s.recent_turn_hashes('one')
        self.assertIsNone(self.s.find_session_by_turn_tail(tail))
        self.assertIsNone(self.s.find_session_by_turn_tail([('not-user','not-assistant')]*2))
    def test_find_session_by_turn_tail_respects_recent_session_bound_and_ignores_incomplete(self):
        self.s.append_turn('older','u1','a1'); self.s.append_turn('older','u2','a2')
        tail=self.s.recent_turn_hashes('older')
        self.s.append_message('newer',1,'user','only user')
        self.assertIsNone(self.s.find_session_by_turn_tail(tail,max_sessions=1))
        self.assertEqual(self.s.find_session_by_turn_tail(tail,max_sessions=2),'older')
    def test_concurrent_completed_turns_are_serialized_in_sqlite(self):
        def write(i): return self.s.append_turn('s',f'u{i}',f'a{i}',1)[0]
        with ThreadPoolExecutor(max_workers=8) as pool:
            turns=list(pool.map(write,range(20)))
        self.assertEqual(sorted(turns),list(range(1,21)))
        self.assertEqual(self.s.latest_turn('s'),20)
        self.assertEqual(len(self.s.unextracted_messages('s')),40)
    def test_cache_off_and_longest_name_scanner(self):
        self.s.add_item(kind='entity',subtype='person',name='Ann',content='Ann')
        self.s.add_item(kind='entity',subtype='person',name='Annabelle',content='Annabelle')
        self.assertEqual(NameScanner().scan('Annabelle?', ['Ann','Annabelle']), ['Annabelle'])
        self.s.retrieve(None,'Tell me about Annabelle?'); calls=self.e.calls
        os.environ['RAG_CACHE']='off'
        try: self.s.retrieve(None,'Tell me about Annabelle?')
        finally: os.environ.pop('RAG_CACHE',None)
        self.assertGreater(self.e.calls,calls)
    def test_batch_rollback_leaves_journal_unextracted(self):
        mid=self.s.append_message('s',1,'user','extract me')
        bad={'op':'ADD_FACT','sourceTurnNumber':1,'alias':'f0','subtype':'trait','content':'x','subjectAliases':['e404'],'turnRange':[1,1],'reason':None}
        with self.assertRaises(ValueError): self.s.apply_extraction_batch('s',[bad],{},[mid],mid)
        self.assertEqual(len(self.s.unextracted_messages('s')),1)
    def test_embedding_contract_reindexes_stale_or_changed_vectors(self):
        mid=self.s.add_item(kind='entity',subtype='person',name='Ada',content='person')
        first=self.s.ensure_embedding_contract('model-a@one',2)
        self.assertTrue(first['ready'])
        with self.s._session() as connection:
            connection.execute("UPDATE memory SET content_hash='stale',vector=? WHERE id=?",(pack_vector([1.]),mid))
        repaired=self.s.ensure_embedding_contract('model-a@one',2)
        changed=self.s.ensure_embedding_contract('model-b@two',2)
        self.assertEqual((repaired['failed'],changed['failed']),(0,0))
        with self.s._session() as connection:
            row=connection.execute('SELECT content,content_hash,vector FROM memory WHERE id=?',(mid,)).fetchone()
            meta=dict(connection.execute("SELECT key,value FROM metadata WHERE key IN ('embedding_model','embedding_dim')").fetchall())
        self.assertEqual(row['content_hash'],__import__('hashlib').sha256(row['content'].encode()).hexdigest())
        self.assertEqual(len(row['vector']),8)
        self.assertEqual(meta,{'embedding_model':'model-b@two','embedding_dim':'2'})
    def test_extraction_coverage_requires_each_stage_a_index_exactly_once(self):
        entity=self.s.add_item(kind='entity',subtype='person',name='Ada',content='a',session_id='s')
        ids=list(self.s.append_turn('s','u','a',1)[1:])
        extracted=[
            {'turnNumber':1,'kind':'fact','subtype':'trait','subjectNames':['Ada'],'content':'likes stars','turnRange':[1,1]},
            {'turnNumber':1,'kind':'fact','subtype':'trait','subjectNames':['Ada'],'content':'likes tea','turnRange':[1,1]},
        ]
        duplicate=[
            {'op':'NOOP','sourceItemIndex':0,'sourceTurnNumber':1,'alias':'f0'},
            {'op':'NOOP','sourceItemIndex':0,'sourceTurnNumber':1,'alias':'f0'},
        ]
        fact=self.s.add_item(kind='fact',subtype='trait',content='old',session_id='s',subject_ids=[entity])
        with self.assertRaises(ValueError):
            self.s.apply_extraction_batch('s',duplicate,{'f0':fact},ids,1,extracted_items=extracted)
        self.assertEqual(len(self.s.unextracted_messages('s')),2)
    def test_extraction_rejects_turn_outside_batch_and_reversed_relation(self):
        ada=self.s.add_item(kind='entity',subtype='person',name='Ada',content='a',session_id='s')
        bob=self.s.add_item(kind='entity',subtype='person',name='Bob',content='b',session_id='s')
        _,user_id,assistant_id=self.s.append_turn('s','u','a',1)
        future=[{'turnNumber':999,'kind':'entity','subtype':'person','name':'Eve','content':'e'}]
        future_op=[{'op':'ADD_ENTITY','sourceItemIndex':0,'sourceTurnNumber':999,'alias':'e9','subtype':'person','name':'Eve','content':'e','turnRange':None,'reason':None}]
        with self.assertRaises(ValueError):
            self.s.apply_extraction_batch('s',future_op,{},[user_id,assistant_id],1,extracted_items=future)
        relation=[{'turnNumber':1,'kind':'relation','subtype':'friend','sourceName':'Ada','targetName':'Bob','content':'friends'}]
        reversed_op=[{'op':'ADD_RELATION','sourceItemIndex':0,'sourceTurnNumber':1,'alias':'r9','subtype':'friend','sourceAlias':'e1','targetAlias':'e0','content':'friends','reason':None}]
        with self.assertRaises(ValueError):
            self.s.apply_extraction_batch('s',reversed_op,{'e0':ada,'e1':bob},[user_id,assistant_id],1,extracted_items=relation)
        self.assertEqual(len(self.s.unextracted_messages('s')),2)

if __name__=='__main__': unittest.main()
