from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    """
    Custom pagination that adds total_pages and current_page to every response.
    Supports ?page_size= query param so callers can override the default.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def get_paginated_response(self, data):
        return Response({
            'pagination': {
                'count':        self.page.paginator.count,
                'total_pages':  self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size':    self.get_page_size(self.request),
                'next':         self.get_next_link(),
                'previous':     self.get_previous_link(),
            },
            'results': data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'pagination': {'type': 'object'},
                'results': schema,
            }
        }