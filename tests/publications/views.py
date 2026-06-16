import logging

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Author, Book
from .serializers import AuthorSerializer, BookSerializer

app_logger = logging.getLogger("app.publications")


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer

    def perform_create(self, serializer):
        app_logger.info("Creating author via API")
        super().perform_create(serializer)

    @action(detail=True, methods=["patch"])
    def update_experience(self, request, pk=None):
        """Custom action to update author experience"""
        author = self.get_object()
        experience = request.data.get("experience", "")
        author.experience = experience
        author.save()
        serializer = self.get_serializer(author)
        return Response(serializer.data)


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    @action(detail=True, methods=["patch"])
    def update_title(self, request, pk=None):
        """Custom action to update book title"""
        book = self.get_object()
        title = request.data.get("title", "")
        book.title = title
        book.save()
        serializer = self.get_serializer(book)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="add_co_author")
    def add_co_author(self, request, pk=None):
        """Add a co-author M2M relationship within the request context."""
        book = self.get_object()
        co_author_id = request.data.get("co_author_id")
        co_author = Author.objects.get(pk=co_author_id)
        book.co_authors.add(co_author)
        return Response({"status": "co_author added"})
