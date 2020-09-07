import types
from owlready2 import Not, AllDisjoint
from .concept import Concept
import concurrent.futures
import owlready2


class ConceptGenerator:
    """

    Let the followings be given,

        * I=(\Delta, ^I) an interpretation
        * \Delta the domain of the interpretation
        * ^I  is the interpretation function
        * C is a primitive concept
        * R a relation/ property.

        We refer to [1]



        Resources
        [1] DL-FOIL Concept Learning in Description Logics



    """

    def __init__(self, concepts, T, Bottom, onto, max_size_of_concept, min_size_of_concept):

        assert max_size_of_concept
        assert min_size_of_concept

        self.min_size_of_concept = min_size_of_concept
        self.max_size_of_concept = max_size_of_concept
        self.namespace_base_iri='https://dice-research.org/'

        self.concepts = concepts
        self.T = T
        self.Bottom = Bottom
        self.onto = onto
        # TODO Have a data structure that can only be written once.
        self.log_of_intersections = dict()
        self.log_of_unions = dict()
        self.log_of_negations = dict()
        self.log_of_universal_restriction = dict()
        self.log_of_existential_restriction = dict()

        self.executor = concurrent.futures.ProcessPoolExecutor()

    @staticmethod
    def __concepts_sorter(A, B):
        if len(A) < len(B):
            return A, B
        if len(A) > len(B):
            return B, A

        args = [A, B]
        args.sort(key=lambda ce: ce.str)
        return args[0], args[1]

    @staticmethod
    def type_enrichment(instances, new_concept):
        for i in instances:
            i.is_a.append(new_concept)

    def get_instances_for_restrictions(self, exist, role, filler):
        if exist:
            temp = set()
            # {(x,y) | (x,r,y) \in G}.
            for x, y in role.get_relations():
                if y in filler.instances:
                    temp.add(x)
            return temp
        else:
            temp = set()
            # {(s,o) | (s,r,o) \in G}.
            for s, o in role.get_relations():
                if not (o in filler.instances):
                    temp.add(o)
            return self.T.instances - temp

    def negation(self, concept: Concept) -> Concept:
        """
        ¬C = \Delta^I \ C.
        @param concept: an instance of Concept class
        @return: ¬C: an instance of Concept class
        """
        if concept in self.log_of_negations:
            return self.log_of_negations[concept]

        if not (concept.owl.name == 'Thing'):
            possible_instances_ = self.T.instances - concept.instances

            with self.onto:
                not_concept = types.new_class(name="¬{0}".format(concept.owl.name), bases=(self.T.owl,))
                not_concept.namespace.base_iri = self.namespace_base_iri#concept.owl.namespace.base_iri
                AllDisjoint([not_concept, concept.owl])
                not_concept.is_a.append(Not(concept.owl))

                c = Concept(concept=not_concept, kwargs={'form': 'ObjectComplementOf', 'root': concept})
                c.instances = possible_instances_  # self.T.instances - concept.instances

                self.log_of_negations[concept] = c
                self.concepts[c.full_iri] = c

            return self.log_of_negations[concept]
        elif concept.form == 'ObjectComplementOf':
            assert concept.str[0] == '¬'
            full_iri = concept.owl.namespace.base_iri + concept.owl.name[1:]
            return self.concepts[full_iri]
        elif concept.owl.name == 'Thing':
            self.log_of_negations[concept.full_iri] = self.Bottom
            self.log_of_negations[self.Bottom.full_iri] = concept
            return self.log_of_negations[concept.full_iri]
        else:
            raise ValueError

    def existential_restriction(self, concept: Concept, relation, base=None) -> Concept:
        """
        ∃R.C =>  {x \in \Delta | ∃y \in \Delta : (x, y) \in R^I AND y ∈ C^I }

        @param concept: an instance of Concept
        @param relation: an isntance of owlready2.prop.ObjectPropertyClass'
        @param base:
        @return:
        """

        if (concept, relation) in self.log_of_existential_restriction:
            return self.log_of_existential_restriction[(concept, relation)]

        if not base:
            base = self.T.owl

        possible_instances_ = self.get_instances_for_restrictions(True, relation, concept)

        if not (self.max_size_of_concept >= len(possible_instances_) >= self.min_size_of_concept):
            return self.Bottom

        with self.onto:
            new_concept = types.new_class(name="(∃{0}.{1})".format(relation.name, concept.str), bases=(base,))
            new_concept.namespace.base_iri = self.namespace_base_iri
            new_concept.is_a.append(relation.some(concept.owl))
            # new_concept.equivalent_to.append(relation.some(concept.owl))
            # relation.range.append(concept.owl) # TODO is it really important ?
            # relation.domain.append(base)# TODO: is it really important ?
            # self.type__restrictions_enrichments(True, relation, concept, new_concept)
            # self.executor.submit(self.type__restrictions_enrichments, (True, relation, concept, new_concept))

            c = Concept(concept=new_concept,
                        kwargs={'form': 'ObjectSomeValuesFrom', 'Role': relation, 'Filler': concept})

            for i in possible_instances_:
                assert type(i) is not str
            c.instances = possible_instances_  # self.get_instances_for_restrictions(True, relation, concept)

            self.log_of_existential_restriction[(concept, relation)] = c
            self.concepts[c.full_iri] = c

        return self.log_of_existential_restriction[(concept, relation)]

    def universal_restriction(self, concept: Concept, relation, base=None) -> Concept:
        """

        ∀R.C => extension => {x \in \Delta | ∃y \in \Delta : (x, y) ∈ \in R^I \implies y ∈ C^I }

        Brief explanation:
                    The universal quantifier defines a class as
                    *   The set of all instances for which the given role "only" attains values from the given class.

        :param concept:
        :param relation:
        :param base:
        :return:
        """

        if (concept, relation) in self.log_of_universal_restriction:
            return self.log_of_universal_restriction[(concept, relation)]

        if not base:
            base = self.T.owl

        possible_instances_ = self.get_instances_for_restrictions(False, relation, concept)

        if not (self.max_size_of_concept >= len(possible_instances_) >= self.min_size_of_concept):
            return self.Bottom

        with self.onto:
            new_concept = types.new_class(name="(∀{0}.{1})".format(relation.name, concept.str), bases=(base,))
            new_concept.namespace.base_iri = self.namespace_base_iri

            new_concept.is_a.append(relation.only(base))
            # new_concept.equivalent_to.append(relation.only(base))
            # relation.range.append(concept.owl) # TODO is it really important ?
            # relation.domain.append(base)# TODO: is it really important ?
            # self.type__restrictions_enrichments(False, relation, concept, new_concept)

            # self.executor.submit(self.type__restrictions_enrichments, (False, relation, concept, new_concept))
            c = Concept(concept=new_concept,
                        kwargs={'form': 'ObjectAllValuesFrom', 'Role': relation, 'Filler': concept})

            for i in possible_instances_:
                assert type(i) is not str
            c.instances = possible_instances_  # self.get_instances_for_restrictions(False, relation, concept)

            self.log_of_universal_restriction[(concept, relation)] = c

            self.concepts[c.full_iri] = c

        return self.log_of_universal_restriction[(concept, relation)]

    def union(self, A: Concept, B: Concept, base=None):

        A, B = self.__concepts_sorter(A, B)

        # Crude workaround
        if A.str == 'Nothing':
            return B

        if B.str == 'Nothing':
            return A

        if (A, B) in self.log_of_unions:
            return self.log_of_unions[(A, B)]

        if not base:
            base = self.T.owl

        possible_instances_ = A.instances | B.instances

        if not (self.max_size_of_concept >= len(possible_instances_) >= self.min_size_of_concept):
            return self.Bottom

        with self.onto:
            new_concept = types.new_class(name="({0} ⊔ {1})".format(A.str, B.str), bases=(base,))
            new_concept.namespace.base_iri = self.namespace_base_iri

            new_concept.is_a.append(A.owl | B.owl)
            c = Concept(concept=new_concept, kwargs={'form': 'ObjectUnionOf', 'ConceptA': A, 'ConceptB': B})

            for i in possible_instances_:
                assert type(i) is not str

            c.instances = possible_instances_  # A.instances | B.instances
            self.log_of_unions[(A, B)] = c

            self.concepts[c.full_iri] = c
        return self.log_of_unions[(A, B)]

    def intersection(self, A: Concept, B: Concept, base=None) -> Concept:
        A, B = self.__concepts_sorter(A, B)

        if (A, B) in self.log_of_intersections:
            return self.log_of_intersections[(A, B)]

        # Crude workaround
        if A.str == 'Nothing' or B.str == 'Nothing':
            self.log_of_intersections[(A, B)] = self.Bottom
            return self.log_of_intersections[(A, B)]

        if not base:
            base = self.T.owl

        possible_instances_ = A.instances & B.instances

        if not (self.max_size_of_concept >= len(possible_instances_) >= self.min_size_of_concept):
            return self.Bottom

        with self.onto:
            new_concept = types.new_class(name="({0}  ⊓  {1})".format(A.str, B.str), bases=(base,))
            new_concept.namespace.base_iri = self.namespace_base_iri

            new_concept.is_a.append(A.owl & B.owl)

            c = Concept(concept=new_concept, kwargs={'form': 'ObjectIntersectionOf', 'ConceptA': A, 'ConceptB': B})

            for i in possible_instances_:
                assert type(i) is not str

            c.instances = possible_instances_  # A.instances & B.instances
            self.log_of_intersections[(A, B)] = c
            self.concepts[c.full_iri] = c

        return self.log_of_intersections[(A, B)]
