from rest_framework import viewsets
from .models import Review
from .serializers import ReviewSerializer
from rest_framework.response import Response
from rest_framework import status
from django.db import DatabaseError
from rest_framework.views import APIView
# Create your views here.


class ReviewViewSet(APIView):
    serializer_class = ReviewSerializer
    def get(self, request):
        reviews = Review.objects.filter(is_active=True)
        if reviews.exists():
            serializer = ReviewSerializer(reviews, many=True)
            return Response(serializer.data)
        else:
            return Response({'error': 'No reviews found'}, status=status.HTTP_204_NO_CONTENT)