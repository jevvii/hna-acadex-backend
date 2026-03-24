from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Standard pagination for most list endpoints."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'results': data,
            'pagination': {
                'page': self.page.number,
                'page_size': self.page_size,
                'total_pages': self.page.paginator.num_pages,
                'total_count': self.page.paginator.count,
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous(),
            }
        })


class NotificationPagination(CursorPagination):
    """Cursor-based pagination for notifications (chronological)."""
    page_size = 20
    ordering = '-created_at'
    cursor_query_param = 'cursor'


class CoursePagination(PageNumberPagination):
    """Pagination for course lists."""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50