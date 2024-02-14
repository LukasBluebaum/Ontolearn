"""Triple store representations."""
import logging
import re
from itertools import chain
from typing import Iterable
import requests
from requests import Response
from requests.exceptions import RequestException, JSONDecodeError
from owlapy.owl2sparql.converter import Owl2SparqlConverter
from ontolearn.base.ext import OWLReasonerEx
from ontolearn.knowledge_base import KnowledgeBase
from owlapy.model import OWLObjectPropertyRangeAxiom, OWLDataProperty, \
    OWLNamedIndividual, OWLClassExpression, OWLObjectPropertyExpression, OWLOntologyID, OWLOntology, \
    OWLThing, OWLObjectPropertyDomainAxiom, OWLLiteral, \
    OWLObjectInverseOf, OWLClass, \
    IRI, OWLDataPropertyRangeAxiom, OWLDataPropertyDomainAxiom, OWLClassAxiom, \
    OWLEquivalentClassesAxiom,  OWLObjectProperty, OWLProperty, OWLDatatype


logger = logging.getLogger(__name__)

rdfs_prefix = "PREFIX  rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n "
owl_prefix = "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n "
rdf_prefix = "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n "


def is_valid_url(url) -> bool:
    """
    Check the validity of a URL.

    Args:
        url (str): The url to validate.

    Returns:
        True if url is not None, and it passes the regex check.

    """
    regex = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url is not None and regex.search(url)


def get_results_from_ts(triplestore_address: str, query: str, return_type: type):
    """
    Execute the SPARQL query in the given triplestore_address and return the result as the given return_type.

    Args:
        triplestore_address (str): The triplestore address where the query will be executed.
        query (str): SPARQL query where the root variable should be '?x'.
        return_type (type): OWLAPY class as type. e.g. OWLClass, OWLNamedIndividual, etc.

    Returns:
        Generator containing the results of the query as the given type.
    """
    try:
        response = requests.post(triplestore_address, data={'query': query})
    except RequestException as e:
        raise RequestException(f"Make sure the server is running on the `triplestore_address` = '{triplestore_address}'"
                               f". Check the error below:"
                               f"\n  -->Error: {e}")
    try:
        if return_type == OWLLiteral:
            yield from unwrap(response)
        else:
            yield from [return_type(i) for i in unwrap(response)]
        # return [return_type(IRI.create(i['x']['value'])) for i in
        #         response.json()['results']['bindings']]
    except JSONDecodeError as e:
        raise JSONDecodeError(f"Something went wrong with decoding JSON from the response. Check for typos in "
                              f"the `triplestore_address` = '{triplestore_address}' otherwise the error is likely "
                              f"caused by an internal issue. \n  -->Error: {e}")


def unwrap(result: Response):
    json = result.json()
    vars_ = list(json['head']['vars'])
    for b in json['results']['bindings']:
        val = []
        for v in vars_:
            if b[v]['type'] == 'uri':
                val.append(IRI.create(b[v]['value']))
            else:
                val.append(OWLLiteral(b[v]['value'], OWLDatatype(IRI.create(b[v]['datatype']))))
        if len(val) == 1:
            yield val.pop()
        else:
            yield tuple(val)


def suf(direct: bool):
    """Put the star for rdfs properties depending on direct param"""
    return " " if direct else "* "


class TripleStoreOntology(OWLOntology):

    def __init__(self, triplestore_address: str):
        assert (is_valid_url(triplestore_address)), "You should specify a valid URL in the following argument: " \
                                                    "'triplestore_address' of class `TripleStore`"

        self.url = triplestore_address

    def classes_in_signature(self) -> Iterable[OWLClass]:
        query = owl_prefix + "SELECT DISTINCT ?x WHERE {?x a owl:Class.}"
        yield from get_results_from_ts(self.url, query, OWLClass)

    def data_properties_in_signature(self) -> Iterable[OWLDataProperty]:
        query = owl_prefix + "SELECT DISTINCT ?x\n " + "WHERE {?x a owl:DatatypeProperty.}"
        yield from get_results_from_ts(self.url, query, OWLDataProperty)

    def object_properties_in_signature(self) -> Iterable[OWLObjectProperty]:
        query = owl_prefix + "SELECT DISTINCT ?x\n " + "WHERE {?x a owl:ObjectProperty.}"
        yield from get_results_from_ts(self.url, query, OWLObjectProperty)

    def individuals_in_signature(self) -> Iterable[OWLNamedIndividual]:
        query = owl_prefix + "SELECT DISTINCT ?x\n " + "WHERE {?x a owl:NamedIndividual.}"
        yield from get_results_from_ts(self.url, query, OWLNamedIndividual)

    def equivalent_classes_axioms(self, c: OWLClass) -> Iterable[OWLEquivalentClassesAxiom]:
        query = owl_prefix + "SELECT DISTINCT ?x" + \
                "WHERE { ?x owl:equivalentClass " + f"<{c.get_iri().as_str()}>." + \
                "FILTER(?x != " + f"<{c.get_iri().as_str()}>)}}"
        for cls in get_results_from_ts(self.url, query, OWLClass):
            yield OWLEquivalentClassesAxiom([c, cls])

    def general_class_axioms(self) -> Iterable[OWLClassAxiom]:
        raise NotImplementedError

    def data_property_domain_axioms(self, pe: OWLDataProperty) -> Iterable[OWLDataPropertyDomainAxiom]:
        domains = self._get_property_domains(pe)
        if len(domains) == 0:
            yield OWLDataPropertyDomainAxiom(pe, OWLThing)
        else:
            for dom in domains:
                yield OWLDataPropertyDomainAxiom(pe, dom)

    def data_property_range_axioms(self, pe: OWLDataProperty) -> Iterable[OWLDataPropertyRangeAxiom]:
        raise NotImplementedError

    def object_property_domain_axioms(self, pe: OWLObjectProperty) -> Iterable[OWLObjectPropertyDomainAxiom]:
        domains = self._get_property_domains(pe)
        if len(domains) == 0:
            yield OWLObjectPropertyDomainAxiom(pe, OWLThing)
        else:
            for dom in domains:
                yield OWLObjectPropertyDomainAxiom(pe, dom)

    def object_property_range_axioms(self, pe: OWLObjectProperty) -> Iterable[OWLObjectPropertyRangeAxiom]:
        query = rdfs_prefix + "SELECT ?x WHERE { " + f"<{pe.get_iri().as_str()}>" + " rdfs:range ?x. }"
        ranges = set(get_results_from_ts(self.url, query, OWLClass))
        if len(ranges) == 0:
            yield OWLObjectPropertyRangeAxiom(pe, OWLThing)
        else:
            for rng in ranges:
                yield OWLObjectPropertyRangeAxiom(pe, rng)

    def _get_property_domains(self, pe: OWLProperty):
        if isinstance(pe, OWLObjectProperty) or isinstance(pe, OWLDataProperty):
            query = rdfs_prefix + "SELECT ?x WHERE { " + f"<{pe.get_iri().as_str()}>" + " rdfs:domain ?x. }"
            domains = set(get_results_from_ts(self.url, query, OWLClass))
            return domains
        else:
            raise NotImplementedError

    def get_owl_ontology_manager(self):
        # no manager for this kind of Ontology
        pass

    def get_ontology_id(self) -> OWLOntologyID:
        # query = (rdf_prefix + owl_prefix +
        #          "SELECT ?ontologyIRI WHERE { ?ontology rdf:type owl:Ontology . ?ontology rdf:about ?ontologyIRI .}")
        # return list(get_results_from_ts(self.url, query, OWLOntologyID)).pop()
        raise NotImplementedError

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return self.url == other.url
        return NotImplemented

    def __hash__(self):
        return hash(self.url)

    def __repr__(self):
        return f'TripleStoreOntology({self.url})'


class TripleStoreReasoner(OWLReasonerEx):
    __slots__ = 'ontology'

    def __init__(self, ontology: TripleStoreOntology):
        self.ontology = ontology
        self.url = self.ontology.url
        self._owl2sparql_converter = Owl2SparqlConverter()

    def data_property_domains(self, pe: OWLDataProperty, direct: bool = False) -> Iterable[OWLClassExpression]:
        domains = {d.get_domain() for d in self.ontology.data_property_domain_axioms(pe)}
        super_domains = set(chain.from_iterable([self.super_classes(d) for d in domains]))
        yield from domains - super_domains
        if not direct:
            yield from super_domains

    def object_property_domains(self, pe: OWLObjectProperty, direct: bool = False) -> Iterable[OWLClassExpression]:
        domains = {d.get_domain() for d in self.ontology.object_property_domain_axioms(pe)}
        super_domains = set(chain.from_iterable([self.super_classes(d) for d in domains]))
        yield from domains - super_domains
        if not direct:
            yield from super_domains

    def object_property_ranges(self, pe: OWLObjectProperty, direct: bool = False) -> Iterable[OWLClassExpression]:
        ranges = {r.get_range() for r in self.ontology.object_property_range_axioms(pe)}
        super_ranges = set(chain.from_iterable([self.super_classes(d) for d in ranges]))
        yield from ranges - super_ranges
        if not direct:
            yield from super_ranges

    def equivalent_classes(self, ce: OWLClassExpression, only_named: bool = True) -> Iterable[OWLClassExpression]:
        if only_named:
            if isinstance(ce, OWLClass):
                query = owl_prefix + "SELECT DISTINCT ?x" + \
                           "WHERE { ?x owl:equivalentClass " + f"<{ce.get_iri().as_str()}>." + \
                           "FILTER(?x != " + f"<{ce.get_iri().as_str()}>)}}"
                yield from get_results_from_ts(self.url, query, OWLClass)
            else:
                raise NotImplementedError("Equivalent classes for complex class expressions is not implemented")
        else:
            raise NotImplementedError("Finding equivalent complex classes is not implemented")

    def disjoint_classes(self, ce: OWLClassExpression, only_named: bool = True) -> Iterable[OWLClassExpression]:
        if only_named:
            if isinstance(ce, OWLClass):
                query = owl_prefix + " SELECT DISTINCT ?x " + \
                        "WHERE { " + f"<{ce.get_iri().as_str()}>" + " owl:disjointWith ?x .}"
                yield from get_results_from_ts(self.url, query, OWLClass)
            else:
                raise NotImplementedError("Disjoint classes for complex class expressions is not implemented")
        else:
            raise NotImplementedError("Finding disjoint complex classes is not implemented")

    def different_individuals(self, ind: OWLNamedIndividual) -> Iterable[OWLNamedIndividual]:
        query = owl_prefix + "SELECT DISTINCT ?x" + \
                "WHERE { ?x owl:distinctMembers " + f"<{ind.str}>" + " .}"
        yield from get_results_from_ts(self.url, query, OWLNamedIndividual)

    def same_individuals(self, ind: OWLNamedIndividual) -> Iterable[OWLNamedIndividual]:
        query = owl_prefix + "SELECT DISTINCT ?x" + \
                "WHERE { ?x owl:sameAs " + f"<{ind.str}>" + " .}"
        yield from get_results_from_ts(self.url, query, OWLNamedIndividual)

    def equivalent_object_properties(self, op: OWLObjectPropertyExpression) -> Iterable[OWLObjectPropertyExpression]:
        if isinstance(op, OWLObjectProperty):
            query = owl_prefix + "SELECT DISTINCT ?x" + \
                    "WHERE { ?x owl:equivalentProperty " + f"<{op.get_iri().as_str()}>." + \
                    "FILTER(?x != " + f"<{op.get_iri().as_str()}>)}}"
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)
        elif isinstance(op, OWLObjectInverseOf):
            query = owl_prefix + "SELECT DISTINCT ?x" + \
                    "WHERE {  ?inverseProperty owl:inverseOf " + f"<{op.get_inverse().get_iri().as_str()}> ." + \
                    " ?x owl:equivalentProperty ?inverseProperty ." + \
                    "FILTER(?x != ?inverseProperty }>)}"
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)

    def equivalent_data_properties(self, dp: OWLDataProperty) -> Iterable[OWLDataProperty]:
        query = owl_prefix + "SELECT DISTINCT ?x" + \
                "WHERE { ?x owl:equivalentProperty " + f"<{dp.get_iri().as_str()}>." + \
                "FILTER(?x != " + f"<{dp.get_iri().as_str()}>)}}"
        yield from get_results_from_ts(self.url, query, OWLDataProperty)

    def data_property_values(self, ind: OWLNamedIndividual, pe: OWLDataProperty, direct: bool = True) \
            -> Iterable[OWLLiteral]:
        query = "SELECT ?x WHERE { " + f"<{ind.str}>" + f"<{pe.get_iri().as_str()}>" + " ?x . }"
        yield from get_results_from_ts(self.url, query, OWLLiteral)
        if not direct:
            for prop in self.sub_data_properties(pe):
                yield from self.data_property_values(ind, prop, True)

    def object_property_values(self, ind: OWLNamedIndividual, pe: OWLObjectPropertyExpression, direct: bool = True) \
            -> Iterable[OWLNamedIndividual]:
        if isinstance(pe, OWLObjectProperty):
            query = "SELECT ?x WHERE { " + f"<{ind.str}> " + f"<{pe.get_iri().as_str()}>" + " ?x . }"
            yield from get_results_from_ts(self.url, query, OWLNamedIndividual)
        elif isinstance(pe, OWLObjectInverseOf):
            query = (owl_prefix + "SELECT ?x WHERE { ?inverseProperty owl:inverseOf " +
                     f"<{pe.get_inverse().get_iri().as_str()}>." +
                     f"<{ind.str}> ?inverseProperty ?x . }}")
            yield from get_results_from_ts(self.url, query, OWLNamedIndividual)
        if not direct:
            for prop in self.sub_object_properties(pe):
                yield from self.object_property_values(ind, prop, True)

    def flush(self) -> None:
        pass

    def instances(self, ce: OWLClassExpression, direct: bool = False) -> Iterable[OWLNamedIndividual]:
        ce_to_sparql = self._owl2sparql_converter.as_query("?x", ce)
        if not direct:
            ce_to_sparql = ce_to_sparql.replace("?x a ", "?x a ?some_cls. \n ?some_cls "
                                                         "<http://www.w3.org/2000/01/rdf-schema#subClassOf>* ")
        yield from get_results_from_ts(self.url, ce_to_sparql, OWLNamedIndividual)

    def sub_classes(self, ce: OWLClassExpression, direct: bool = False, only_named: bool = True) \
            -> Iterable[OWLClassExpression]:
        if not only_named:
            raise NotImplementedError("Finding anonymous subclasses not implemented")
        if isinstance(ce, OWLClass):
            query = rdfs_prefix + \
                    "SELECT ?x WHERE { ?x rdfs:subClassOf" + suf(direct) + f"<{ce.get_iri().as_str()}>" + ". }"
            results = list(get_results_from_ts(self.url, query, OWLClass))
            if ce in results:
                results.remove(ce)
            yield from results
        else:
            raise NotImplementedError("Subclasses of complex classes retrieved via triple store is not implemented")
            # query = "PREFIX  rdfs: <http://www.w3.org/2000/01/rdf-schema#> " \
            #         "SELECT DISTINCT ?x WHERE { ?x rdfs:subClassOf" + suf(direct) + " ?c. \n" \
            #         "?s a ?c . \n"
            # ce_to_sparql_statements = self._owl2sparql_converter.convert("?s", ce)
            # for s in ce_to_sparql_statements:
            #     query = query + s + "\n"
            # query = query + "}"
            # yield from get_results_from_ts(self._triplestore_address, query, OWLClass)

    def super_classes(self, ce: OWLClassExpression, direct: bool = False, only_named: bool = True) \
            -> Iterable[OWLClassExpression]:
        if not only_named:
            raise NotImplementedError("Finding anonymous superclasses not implemented")
        if isinstance(ce, OWLClass):
            if ce == OWLThing:
                return []
            query = rdfs_prefix + \
                "SELECT ?x WHERE { " + f"<{ce.get_iri().as_str()}>" + " rdfs:subClassOf" + suf(direct) + "?x. }"
            results = list(get_results_from_ts(self.url, query, OWLClass))
            if ce in results:
                results.remove(ce)
            if (not direct and OWLThing not in results) or len(results) == 0:
                results.append(OWLThing)
            yield from results
        else:
            raise NotImplementedError("Superclasses of complex classes retrieved via triple store is not "
                                      "implemented")

    def disjoint_object_properties(self, op: OWLObjectPropertyExpression) -> Iterable[OWLObjectPropertyExpression]:
        if isinstance(op, OWLObjectProperty):
            query = owl_prefix + " SELECT DISTINCT ?x " + \
                "WHERE { " + f"<{op.get_iri().as_str()}>" + " owl:propertyDisjointWith ?x .}"
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)
        elif isinstance(op, OWLObjectInverseOf):
            query = owl_prefix + " SELECT DISTINCT ?x " + \
                    "WHERE {  ?inverseProperty owl:inverseOf " + f"<{op.get_inverse().get_iri().as_str()}> ." + \
                    " ?x owl:propertyDisjointWith ?inverseProperty .}"
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)

    def disjoint_data_properties(self, dp: OWLDataProperty) -> Iterable[OWLDataProperty]:
        query = owl_prefix + " SELECT DISTINCT ?x " + \
                "WHERE { " + f"<{dp.get_iri().as_str()}>" + " owl:propertyDisjointWith ?x .}"
        yield from get_results_from_ts(self.url, query, OWLDataProperty)

    def all_data_property_values(self, pe: OWLDataProperty, direct: bool = True) -> Iterable[OWLLiteral]:
        query = "SELECT DISTINCT ?x WHERE { ?y" + f"<{pe.get_iri().as_str()}>" + " ?x . }"
        yield from get_results_from_ts(self.url, query, OWLLiteral)
        if not direct:
            for prop in self.sub_data_properties(pe):
                yield from self.all_data_property_values(prop, True)

    def sub_data_properties(self, dp: OWLDataProperty, direct: bool = False) -> Iterable[OWLDataProperty]:
        query = rdfs_prefix + \
                "SELECT ?x WHERE { ?x rdfs:subPropertyOf" + suf(direct) + f"<{dp.get_iri().as_str()}>" + ". }"
        yield from get_results_from_ts(self.url, query, OWLDataProperty)

    def super_data_properties(self, dp: OWLDataProperty, direct: bool = False) -> Iterable[OWLDataProperty]:
        query = rdfs_prefix + \
                "SELECT ?x WHERE {" + f"<{dp.get_iri().as_str()}>" + " rdfs:subPropertyOf" + suf(direct) + " ?x. }"
        yield from get_results_from_ts(self.url, query, OWLDataProperty)

    def sub_object_properties(self, op: OWLObjectPropertyExpression, direct: bool = False) \
            -> Iterable[OWLObjectPropertyExpression]:
        if isinstance(op, OWLObjectProperty):
            query = (rdfs_prefix + "SELECT ?x WHERE { ?x rdfs:subPropertyOf"
                     + suf(direct) + f"<{op.get_iri().as_str()}> . FILTER(?x != " + f"<{op.get_iri().as_str()}>) }}")
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)
        elif isinstance(op, OWLObjectInverseOf):
            query = (rdfs_prefix + "SELECT ?x " +
                     "WHERE { ?inverseProperty owl:inverseOf " + f"<{op.get_inverse().get_iri().as_str()}> ." +
                     " ?x rdfs:subPropertyOf" + suf(direct) + " ?inverseProperty . }")
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)

    def super_object_properties(self, op: OWLObjectPropertyExpression, direct: bool = False) \
            -> Iterable[OWLObjectPropertyExpression]:
        if isinstance(op, OWLObjectProperty):
            query = (rdfs_prefix + "SELECT ?x WHERE {" + f"<{op.get_iri().as_str()}>" + " rdfs:subPropertyOf"
                     + suf(direct) + " ?x. FILTER(?x != " + f"<{op.get_iri().as_str()}>) }}")
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)
        elif isinstance(op, OWLObjectInverseOf):
            query = (rdfs_prefix + "SELECT ?x " +
                     "WHERE { ?inverseProperty owl:inverseOf " + f"<{op.get_inverse().get_iri().as_str()}> ." +
                     " ?inverseProperty rdfs:subPropertyOf" + suf(direct) + "?x  . }")
            yield from get_results_from_ts(self.url, query, OWLObjectProperty)

    def types(self, ind: OWLNamedIndividual, direct: bool = False) -> Iterable[OWLClass]:
        if direct:
            query = "SELECT ?x WHERE {" + f"<{ind.str}> a" + " ?x. }"
        else:
            query = rdfs_prefix + "SELECT DISTINCT ?x WHERE {" + f"<{ind.str}> a ?cls. " \
                                                                 " ?cls rdfs:subClassOf* ?x}"
        yield from get_results_from_ts(self.url, query, OWLClass)

    def get_root_ontology(self) -> OWLOntology:
        return self.ontology

    def is_isolated(self):
        # not needed here
        pass

    def is_using_triplestore(self):
        """No use! Deprecated."""
        # TODO: Deprecated! Remove after it is removed from OWLReasoner in owlapy
        pass


class TripleStoreKnowledgeBase(KnowledgeBase):

    url: str
    ontology: TripleStoreOntology
    reasoner: TripleStoreReasoner

    def __init__(self, triplestore_address: str):
        self.url = triplestore_address
        self.ontology = TripleStoreOntology(triplestore_address)
        self.reasoner = TripleStoreReasoner(self.ontology)
        super().__init__(ontology=self.ontology, reasoner=self.reasoner)
