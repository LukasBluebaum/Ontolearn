from abc import ABCMeta, abstractmethod

from rdflib import Graph, Literal, RDF, URIRef
from rdflib.namespace import OWL, RDFS
from collections import deque
from owlready2 import get_ontology, World, rdfs, AnnotationPropertyClass

from .refinement_operators import ModifiedCELOERefinement
from .search import Node
from .search import CELOESearchTree
from .metrics import F1
from .heuristics import CELOEHeuristic
import types


class BaseConceptLearner(metaclass=ABCMeta):
    """
    Base class for Concept Learning approaches

    Learning problem definition, Let
        * K = (TBOX, ABOX) be a knowledge base.
        * \ALCConcepts be a set of all ALC concepts.
        * \hypotheses be a set of ALC concepts : \hypotheses \subseteq \ALCConcepts.

        * K_N be a set of all instances.
        * K_C be a set of concepts defined in TBOX: K_C \subseteq \ALCConcepts
        * K_R be a set of properties/relations.

        * E^+, E^- be a set of positive and negative instances and the followings hold
            ** E^+ \cup E^- \subseteq K_N
            ** E^+ \cap E^- = \emptyset

    ##################################################################################################
        The goal is to to learn a set of concepts $\hypotheses \subseteq \ALCConcepts$ such that
              ∀  H \in \hypotheses: { (K \wedge H \models E^+) \wedge  \neg( K \wedge H \models E^-) }.
    ##################################################################################################

    """

    @abstractmethod
    def __init__(self, knowledge_base=None, refinement_operator=None,
                 quality_func=None,
                 heuristic_func=None,
                 search_tree=None,
                 terminate_on_goal=True,
                 iter_bound=10,
                 max_child_length=10,
                 verbose=True, max_num_of_concepts_tested=None, ignored_concepts=None, root_concept=None):
        if ignored_concepts is None:
            ignored_concepts = {}
        assert knowledge_base
        self.kb = knowledge_base
        self.heuristic = heuristic_func
        self.quality_func = quality_func
        self.rho = refinement_operator
        self.search_tree = search_tree
        self.max_num_of_concepts_tested = max_num_of_concepts_tested

        self.concepts_to_ignore = ignored_concepts
        self.start_class = root_concept

        # Memoization
        self.concepts_to_nodes = dict()
        self.iter_bound = iter_bound
        self.terminate_on_goal = terminate_on_goal
        self.verbose = verbose

        if self.rho is None:
            self.rho = ModifiedCELOERefinement(self.kb, max_child_length=max_child_length)
        self.rho.set_concepts_node_mapping(self.concepts_to_nodes)

        if self.heuristic is None:
            self.heuristic = CELOEHeuristic()

        if self.quality_func is None:
            self.quality_func = F1()

        if self.search_tree is None:
            self.search_tree = CELOESearchTree(quality_func=self.quality_func, heuristic_func=self.heuristic)
        else:
            self.search_tree.set_quality_func(self.quality_func)
            self.search_tree.set_heuristic_func(self.heuristic)

        if self.start_class is None:
            self.start_class = self.kb.thing

        assert self.start_class
        assert self.search_tree is not None
        assert self.quality_func
        assert self.heuristic
        assert self.rho

    def __get_metric_key(self, key: str):
        if key == 'quality':
            metric = self.quality_func.name
            attribute = key
        elif key == 'heuristic':
            metric = self.heuristic.name
            attribute = key
        elif key == 'length':
            metric = key
            attribute = key
        else:
            raise ValueError
        return metric, attribute

    def show_best_predictions(self, key='quality', top_n=10, serialize_name=None):
        """ """
        predictions = self.search_tree.show_best_nodes(top_n, key=key)
        if serialize_name is not None:
            if key == 'quality':
                metric = self.quality_func.name
                attribute = key
            elif key == 'heuristic':
                metric = self.heuristic.name
                attribute = key
            elif key == 'length':
                metric = key
                attribute = key
            else:
                raise ValueError

            # create a Graph
            g = Graph()
            for pred_node in predictions:
                concept_hiearhy = deque()
                concept_hiearhy.appendleft(pred_node.parent_node)
                # get a path of hierhary.
                while concept_hiearhy[-1].parent_node is not None:
                    concept_hiearhy.append(concept_hiearhy[-1].parent_node)

                concept_hiearhy.appendleft(pred_node)

                p_quality = URIRef('https://dice-research.org/' + attribute + ':' + metric)

                integer_mapping = {p: str(th) for th, p in enumerate(concept_hiearhy)}
                for th, i in enumerate(concept_hiearhy):
                    # default encoding to utf-8
                    concept = URIRef('https://dice-research.org/' + integer_mapping[i])
                    g.add((concept, RDF.type, RDFS.Class))  # s type Class.
                    g.add((concept, RDFS.label, Literal(i.concept.str)))
                    val = round(getattr(i, attribute), 3)
                    g.add((concept, p_quality, Literal(val)))

                    if i.parent_node:
                        g.add((concept, RDFS.subClassOf,
                               URIRef('https://dice-research.org/' + integer_mapping[i.parent_node])))

                g.serialize(destination=serialize_name, format='nt')

    def extend_ontology(self, top_n_concepts=10, key='quality'):
        """
        1) Obtain top N nodes from search tree.
        2) Extend ABOX by including explicit type information for all instances belonging to concepts (1)
        """
        self.search_tree.sort_search_tree_by_decreasing_order(key=key)
        for (ith, node) in enumerate(self.search_tree):
            if ith <= top_n_concepts:
                self.kb.apply_type_enrichment(node.concept)
            else:
                break

        folder = self.kb.path[:self.kb.path.rfind('/')] + '/'
        kb_name = 'enriched_' + self.kb.name
        self.kb.save(folder + kb_name + '.owl', rdf_format="rdfxml")

    @abstractmethod
    def initialize_root(self):
        pass

    @abstractmethod
    def next_node_to_expand(self, *args, **kwargs):
        pass

    @abstractmethod
    def apply_rho(self, *args, **kwargs):
        pass

    @abstractmethod
    def predict(self, *args, **kwargs):
        pass

    @property
    def number_of_tested_concepts(self):
        return self.quality_func.applied


# TODO Remove SampleConceptLearner in the next refactoring.
"""class SampleConceptLearner:
    def __init__(self, knowledge_base, max_child_length=5, terminate_on_goal=True, verbose=True, iter_bound=10):
        self.kb = knowledge_base

        self.concepts_to_nodes = dict()
        self.rho = ModifiedCELOERefinement(self.kb, max_child_length=max_child_length)
        self.rho.set_concepts_node_mapping(self.concepts_to_nodes)

        self.verbose = verbose
        # Default values
        self.iter_bound = iter_bound
        self._start_class = self.kb.thing
        self.search_tree = None
        self.maxdepth = 10
        self.max_he, self.min_he = 0, 0
        self.terminate_on_goal = terminate_on_goal

        self.heuristic = CELOEHeuristic()

    def apply_rho(self, node: Node):
        assert isinstance(node, Node)
        self.search_tree.update_prepare(node)
        refinements = [self.rho.getNode(i, parent_node=node)
                       for i in self.rho.refine(node, maxlength=node.h_exp + 1, current_domain=self._start_class)]

        node.increment_h_exp()
        node.refinement_count = len(refinements)  # This should be postpone so that we make make use of generator
        self.heuristic.apply(node)

        self.search_tree.update_done(node)
        return refinements

    def updateMinMaxHorizExp(self, node: Node):
        he = node.h_exp
        # update maximum value
        self.max_he = self.max_he if self.max_he > he else he

        if self.min_he == he - 1:
            threshold_score = node.heuristic + 1 - node.quality
            sorted_x = sorted(self.search_tree.nodes.items(), key=lambda kv: kv[1].heuristic, reverse=True)
            self.search_tree.nodes = dict(sorted_x)

            for item in self.search_tree:
                if node.concept.str != item.concept.str:
                    if item.h_exp == self.min_he:
                        return
                    if self.search_tree[item].heuristic < threshold_score:
                        break
            # inc. minimum since we found no other node which also has min. horiz. exp.
            self.min_he += 1
            print("minimum horizontal expansion is now ", self.min_he)

    def predict(self, pos, neg):
        self.search_tree = CELOESearchTree(quality_func=F1(pos=pos, neg=neg), heuristic_func=self.heuristic)

        self.initialize_root()

        for j in range(1, self.iter_bound):

            node_to_expand = self.next_node_to_expand(j)
            h_exp = node_to_expand.h_exp
            for ref in self.apply_rho(node_to_expand):
                if (len(ref) > h_exp) and ref.depth < self.maxdepth:
                    is_added, goal_found = self.search_tree.add_node(ref)
                    if is_added:
                        node_to_expand.add_children(ref)
                    if goal_found:
                        print(
                            'Goal found after {0} number of concepts tested.'.format(self.search_tree.expressionTests))
                        if self.terminate_on_goal:
                            return True
            self.updateMinMaxHorizExp(node_to_expand)"""
