from ontolearn.ea_algorithms import AbstractEvolutionaryAlgorithm, EASimple
from ontolearn.ea_initialization import AbstractEAInitialization, EARandomInitialization
from ontolearn.search import EvoLearnerNode
from ontolearn.fitness_functions import LinearPressureFitness
from ontolearn.metrics import Accuracy
from owlapy.render import DLSyntaxObjectRenderer
from ontolearn.learning_problem import EncodedPosNegLPStandard, PosNegLPStandard
from ontolearn.base_concept_learner import BaseConceptLearner
from ontolearn.abstracts import AbstractFitness, AbstractScorer
from typing import Callable, Optional
from ontolearn.knowledge_base import KnowledgeBase
import operator

from deap import base, creator, tools, gp

from owlapy.model import OWLClassExpression, OWLObjectPropertyExpression
import time


class EvoLearner(BaseConceptLearner[EvoLearnerNode]):

    __slots__ = 'fitness_func', 'init_method', 'algorithm', 'expressivity', 'tournament_size',  \
                'population_size', 'num_generations', 'height_limit', 'pset', 'toolbox', \
                '_learning_problem', 'result_population'

    name = 'evolearner'

    fitness_func: AbstractFitness
    init_method: AbstractEAInitialization
    algorithm: AbstractEvolutionaryAlgorithm
    expressivity: str
    tournament_size: int
    population_size: int
    num_generations: int
    height_limit: int

    pset: gp.PrimitiveSetTyped
    toolbox: base.Toolbox
    _learning_problem: EncodedPosNegLPStandard

    def __init__(self,
                 knowledge_base: KnowledgeBase,
                 quality_func: Optional[AbstractScorer] = None,
                 fitness_func: Optional[AbstractFitness] = None,
                 init_method: Optional[AbstractEAInitialization] = None,
                 algorithm: Optional[AbstractEvolutionaryAlgorithm] = None,
                 terminate_on_goal: Optional[bool] = None,
                 max_runtime: Optional[int] = None,
                 expressivity: Optional[str] = None,
                 tournament_size: Optional[int] = None,
                 population_size: Optional[int] = None,
                 num_generations: Optional[int] = None,
                 height_limit: Optional[int] = None):

        if quality_func is None:
            quality_func = Accuracy()

        super().__init__(knowledge_base=knowledge_base,
                         quality_func=quality_func,
                         terminate_on_goal=terminate_on_goal,
                         max_runtime=max_runtime)

        self.fitness_func = fitness_func
        self.init_method = init_method
        self.algorithm = algorithm
        self.expressivity = expressivity
        self.tournament_size = tournament_size
        self.population_size = population_size
        self.num_generations = num_generations
        self.height_limit = height_limit

        self.result_population = None

        self.__setup()

    def __setup(self):

        if self.fitness_func is None:
            self.fitness_func = LinearPressureFitness()

        if self.init_method is None:
            self.init_method = EARandomInitialization()

        if self.algorithm is None:
            self.algorithm = EASimple()

        if self.expressivity is None:
            self.expressivity = "ALC"

        if self.tournament_size is None:
            self.tournament_size = 7

        if self.population_size is None:
            self.population_size = 800

        if self.num_generations is None:
            self.num_generations = 200

        if self.height_limit is None:
            self.height_limit = 17

        self.pset = self.__build_primitive_set()
        self.toolbox = self.__build_toolbox()

    def __build_primitive_set(self) -> gp.PrimitiveSetTyped:

        ontology = self.kb.ontology()
        factory = PrimitiveFactory(self.kb)
        union = factory.create_union()
        intersection = factory.create_intersection()

        pset = gp.PrimitiveSetTyped("concept_tree", [], OWLClassExpression)
        pset.addPrimitive(self.kb.negation, [OWLClassExpression], OWLClassExpression,
                          name='negation')
        pset.addPrimitive(union, [OWLClassExpression, OWLClassExpression], OWLClassExpression,
                          name="union")
        pset.addPrimitive(intersection, [OWLClassExpression, OWLClassExpression], OWLClassExpression,
                          name="intersection")

        for property_ in ontology.object_properties_in_signature():
            name = property_.get_iri().get_remainder()
            existential, universal = factory.create_existential_universal(property_)
            pset.addPrimitive(existential, [OWLClassExpression], OWLClassExpression, name="exists" + name)
            pset.addPrimitive(universal, [OWLClassExpression], OWLClassExpression, name="forall" + name)

        for class_ in ontology.classes_in_signature():
            pset.addTerminal(class_, OWLClassExpression, name=class_.get_iri().get_remainder())

        return pset

    def __build_toolbox(self) -> base.Toolbox:
        creator.create("Fitness", base.Fitness, weights=(1.0,))
        creator.create("Quality", base.Fitness, weights=(1.0,))
        creator.create("Individual", gp.PrimitiveTree, fitness=creator.Fitness, quality=creator.Quality)

        toolbox = base.Toolbox()
        toolbox.register("create_tree", self.init_method.get_individual, pset=self.pset)
        toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.create_tree)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("compile", gp.compile, pset=self.pset)

        toolbox.register("apply_fitness", self._fitness_func)
        toolbox.register("select", tools.selTournament, tournsize=self.tournament_size)
        toolbox.register("mate", gp.cxOnePoint)
        toolbox.register("create_tree_mut", gp.genHalfAndHalf, min_=1, max_=3)
        toolbox.register("mutate", gp.mutUniform, expr=toolbox.create_tree_mut, pset=self.pset)

        toolbox.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"),
                                                max_value=self.height_limit))
        toolbox.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"),
                                                  max_value=self.height_limit))

        toolbox.register("print", self.print_top_n_individuals)
        toolbox.register("terminate_on_goal", lambda: self.terminate_on_goal)
        toolbox.register("max_runtime", lambda: self.max_runtime)
        toolbox.register("pset", lambda: self.pset)

        return toolbox

    def register_op(self, alias: str, function: Callable, *args, **kargs):
        self.toolbox.register(alias, function, *args, **kargs)
        self.toolbox.decorate(alias, gp.staticLimit(key=operator.attrgetter("height"),
                                                    max_value=self.height_limit))

    def fit(self, *args, **kwargs):
        """
        Find hypotheses that explain pos and neg.
        """
        self.clean()
        learning_problem = self.construct_learning_problem(PosNegLPStandard, args, kwargs)
        self._learning_problem = learning_problem.encode_kb(self.kb)

        verbose = kwargs.pop("verbose", False)

        self.start_time = time.time()
        self.result_population = self.toolbox.population(n=self.population_size)
        self._goal_found = self.algorithm.evolve(self.toolbox, 
                                                 self.result_population, 
                                                 self.num_generations,
                                                 self.start_time,
                                                 verbose=verbose)

        return self.terminate()

    # TODO: Think about the node wrapping
    def best_hypotheses(self, n=5, key='fitness'):
        assert self.result_population is not None
        assert len(self.result_population) > 0

        best_inds = tools.selBest(self.result_population, k=n, fit_attr=key)
        best_concepts = [gp.compile(ind, self.pset) for ind in best_inds]

        for con, ind in zip(best_concepts, best_inds):
            individuals_count = len(self.kb.individuals_set(con))
            yield EvoLearnerNode(con, self.kb.cl(con), individuals_count, ind.quality.values[0],
                                 len(ind), ind.height)

    def _fitness_func(self, individual):
        concept = gp.compile(individual, self.pset)
        instances = self.kb.individuals_set(concept)
        quality = self.quality_func.score(instances, self._learning_problem)
        individual.quality.values = (quality[1],)
        self.fitness_func.apply(individual)

    def print_top_n_individuals(self, top_n=5, key='fitness'):
        [print(node) for node in self.best_hypotheses(n=top_n, key=key)]

    def clean(self):
        self.result_population = None
        super().clean()


class PrimitiveFactory:

    __slots__ = 'knowledge_base'

    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base

    def create_union(self):

        def union(A: OWLClassExpression, B: OWLClassExpression) -> OWLClassExpression:
            return self.knowledge_base.union([A, B])

        return union

    def create_intersection(self):

        def intersection(A: OWLClassExpression, B: OWLClassExpression) -> OWLClassExpression:
            return self.knowledge_base.intersection([A, B])

        return intersection

    def create_existential_universal(self, property_: OWLObjectPropertyExpression):

        def existential_restriction(filler: OWLClassExpression) -> OWLClassExpression:
            return self.knowledge_base.existential_restriction(filler, property_)

        def universal_restriction(filler: OWLClassExpression) -> OWLClassExpression:
            return self.knowledge_base.universal_restriction(filler, property_)

        return existential_restriction, universal_restriction
    