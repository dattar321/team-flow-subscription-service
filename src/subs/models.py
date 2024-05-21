from django.contrib.auth.models import User
from django.db import models


class CheckoutSessionRecord(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, help_text='The user who initiated the checkout.'
    )
    stripe_customer_id = models.CharField(max_length=255)
    stripe_checkout_session_id = models.CharField(max_length=255)
    stripe_price_id = models.CharField(max_length=255)
    is_pro = models.BooleanField(default=False)
    is_pro_max = models.BooleanField(default=False)
