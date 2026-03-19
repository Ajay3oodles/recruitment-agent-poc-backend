from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class SignupSerializer(serializers.ModelSerializer):
    # use email instead of username in the signup form
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        # removed username from input fields; username will be set to email
        fields = ('email', 'name', 'phone', 'password')

    def create(self, validated_data):
        # Ensure username exists because the custom User still inherits AbstractUser
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        # set username equal to email to keep compatibility
        user = User.objects.create_user(username=email, email=email, password=password, **validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    # login via email instead of username
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
