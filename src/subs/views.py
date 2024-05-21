import json  # noqa
import os

import stripe
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv

from src.subs import models

load_dotenv()
DOMAIN = 'http://localhost:8005'
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')


def subscribe(request) -> HttpResponse:
    # We login a sample user for the demo.
    user, created = User.objects.get_or_create(username='rohit',
                                               email='rohit@datta.com')
    if created:
        user.set_password('password')
        user.save()
    login(request, user)
    request.user = user

    return render(request, 'subscribe.html')


def cancel(request) -> HttpResponse:
    return render(request, 'cancel.html')


def success(request) -> HttpResponse:

    print(f'{request.session =}')  # noqa

    stripe_checkout_session_id = request.GET['session_id']  # noqa

    return render(request, 'success.html')


def create_checkout_session(request) -> HttpResponse:
    is_pro, is_pro_max = False, False
    product_id = request.POST.get('product_id')

    print(product_id)

    if product_id == 'prod_Q942PDhLs8Okau':
        is_pro = True
    elif product_id == 'prod_Q96BvyJyT8HymN':
        is_pro_max = True

    try:
        # Retrieve the product information
        prices = stripe.Price.list(product=product_id, expand=['data.product'])
        price_item = prices.data[0]
        # print('p', price_item)
        # Create a checkout session with the specified product
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                'price': price_item['id'],
                'quantity': 1
            }],
            mode='subscription',
            success_url=DOMAIN + reverse('success') +
            '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=DOMAIN + reverse('cancel'))

        # Save the checkout session record
        models.CheckoutSessionRecord.objects.create(
            user=request.user,
            stripe_checkout_session_id=checkout_session.id,
            stripe_price_id=price_item.id,
            is_pro_max=is_pro_max,
            is_pro=is_pro,
        )

        # Redirect to the checkout session URL
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print('e', e)
        return HttpResponse('Server error', status=500)


def direct_to_customer_portal(request) -> HttpResponse:
    """
    Creates a customer portal for the user to manage their subscription.
    """
    checkout_record = models.CheckoutSessionRecord.objects.filter(
        user=request.user
    ).last(
    )  # For demo purposes, we get the last checkout session record the user created.

    checkout_session = stripe.checkout.Session.retrieve(
        checkout_record.stripe_checkout_session_id)

    portal_session = stripe.billing_portal.Session.create(
        customer=checkout_session.customer,
        return_url=DOMAIN +
        reverse('subscribe')  # Send the user here from the portal.
    )
    return redirect(portal_session.url, code=303)


@csrf_exempt
def collect_stripe_webhook(request) -> JsonResponse:
    """
    Stripe sends webhook events to this endpoint.
    We verify the webhook signature and updates the database record.
    """
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    signature = request.META['HTTP_STRIPE_SIGNATURE']
    payload = request.body

    try:
        event = stripe.Webhook.construct_event(payload=payload,
                                               sig_header=signature,
                                               secret=webhook_secret)
    except ValueError as e:  # Invalid payload.
        raise ValueError(e)
    except stripe.error.SignatureVerificationError as e:  # Invalid signature
        raise stripe.error.SignatureVerificationError(e)

    _update_record(event)

    return JsonResponse({'status': 'success'})


def _update_record(webhook_event) -> None:
    """
    We update our database record based on the webhook event.

    Use these events to update your database records.
    You could extend this to send emails, update user records, set up different access levels, etc.
    """
    data_object = webhook_event['data']['object']
    event_type = webhook_event['type']

    if event_type == 'checkout.session.completed':
        checkout_record = models.CheckoutSessionRecord.objects.get(
            stripe_checkout_session_id=data_object['id'])
        checkout_record.stripe_customer_id = data_object['customer']
        checkout_record.has_access = True
        checkout_record.save()
        print('🔔 Payment succeeded!')
    elif event_type == 'customer.subscription.created':
        print('🎟️ Subscription created')
    elif event_type == 'customer.subscription.updated':
        print('✍️ Subscription updated')
    elif event_type == 'customer.subscription.deleted':
        checkout_record = models.CheckoutSessionRecord.objects.get(
            stripe_customer_id=data_object['customer'])
        checkout_record.has_access = False
        checkout_record.save()
        print('✋ Subscription canceled: %s', data_object.id)
