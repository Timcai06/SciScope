"""SciScope evaluation suite (retrieval / relevance / trends / recommend).

Lives above both src and backend so it may import either — eval is application
level, which removes the previous src->backend inverted dependency.
"""
