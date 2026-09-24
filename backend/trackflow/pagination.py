from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Page-number pagination that honours `?page_size=`. Boards, backlogs and reports ask for
    a few hundred rows in one request; without `page_size_query_param` DRF silently ignores
    that and caps every list at PAGE_SIZE (50), so boards with more issues dropped cards."""

    page_size_query_param = "page_size"
    max_page_size = 1000
