"""
Defines asynchronous celery task for sending email notification (through edx-ace)
pertaining to new discussion forum comments.
"""
import logging

from celery import task
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

from celery_utils.logged_task import LoggedTask
from edx_ace import ace
from edx_ace.message import MessageType
from edx_ace.recipient import Recipient
from opaque_keys.edx.keys import CourseKey
import lms.lib.comment_client as cc
from lms.lib.comment_client.utils import merge_dict

from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.schedules.template_context import get_base_template_context


log = logging.getLogger(__name__)


DEFAULT_LANGUAGE = 'en'
ROUTING_KEY = getattr(settings, 'ACE_ROUTING_KEY', None)


class ResponseNotification(MessageType):
    def __init__(self, *args, **kwargs):
        super(ResponseNotification, self).__init__(*args, **kwargs)
        self.name = 'response_notification'


@task(base=LoggedTask, routing_key=ROUTING_KEY)
def send_ace_message(context):
    context['course_id'] = CourseKey.from_string(context['course_id'])

    if _should_send_message(context):
        thread_author = User.objects.get(id=context['thread_author_id'])
        message = ResponseNotification().personalize(
            Recipient(thread_author.username, thread_author.email),
            _get_course_language(context['course_id']),
            _build_message_context(context)
        )
        log.info('Sending forum comment email for thread %s with context %s', context['thread_id'], context)
        ace.send(message)


def _should_send_message(context):
    cc_thread_author = cc.User(id=context['thread_author_id'], course_id=context['course_id'])
    return cc_thread_author.is_subscribed_to_thread(context['thread_id'])


def _get_course_language(course_id):
    course_overview = CourseOverview.objects.get(id=course_id)
    language = course_overview.language or DEFAULT_LANGUAGE
    return language


def _build_message_context(context):
    message_context = get_base_template_context(Site.objects.get_current())
    message_context.update(context)
    message_context.update({
        'post_link': None,  # TODO
        'unsubscribe_link': None,  # TODO
    })
    return message_context
