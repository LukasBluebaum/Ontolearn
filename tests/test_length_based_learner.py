""" Test the default pipeline for structured machine learning"""

import json

from ontolearn import CELOEHeuristic
from ontolearn import F1
from ontolearn import KnowledgeBase
from ontolearn import LengthBasedRefinement
from ontolearn import LengthBaseLearner
from ontolearn import SearchTreePriorityQueue


def test_lengthbasedlearner():
    with open('examples/synthetic_problems.json') as json_file:
        settings = json.load(json_file)

    # because '../data/family-benchmark_rich_background.owl'
    kb = KnowledgeBase(path=settings['data_path'][3:])
    for str_target_concept, examples in settings['problems'].items():
        p = set(examples['positive_examples'])
        n = set(examples['negative_examples'])
        print('Target concept: ', str_target_concept)
        concepts_to_ignore = set()
        # lets inject more background info
        if str_target_concept in ['Granddaughter', 'Aunt', 'Sister']:
            concepts_to_ignore.update(
                {'Brother', 'Father', 'Uncle', 'Grandparent'})
            model = LengthBaseLearner(
                knowledge_base=kb,
                refinement_operator=LengthBasedRefinement(kb=kb),
                quality_func=F1(),
                min_length=1,
                heuristic_func=CELOEHeuristic(),
                search_tree=SearchTreePriorityQueue(),
                terminate_on_goal=True,
                iter_bound=1_000,
                max_num_of_concepts_tested=5_000,
                ignored_concepts=concepts_to_ignore,
                verbose=True)

            preds = model.predict(pos=p, neg=n, n=10)
            assert len(preds) > 0