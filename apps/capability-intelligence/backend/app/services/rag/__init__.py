"""Catalogue-grounded RAG (PRD FR-16, TRD §11).

Two services compose the retrieval contract:

- :mod:`catalogue_corpus_builder` — emits one chunk per
  catalogue entity (subcaps, maturity descriptors, stories, L4
  features, themes, personas) into the ``catalogue_ontology`` index.
- :mod:`hybrid_retriever` — BM25 + dense + structured-filter retrieval
  over the indexed corpus, merged via reciprocal-rank fusion.
"""
