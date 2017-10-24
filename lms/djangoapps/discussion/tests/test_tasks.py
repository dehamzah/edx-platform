"""
Tests the execution of forum notification tasks.
"""
from datetime import datetime, timedelta
import json

import ddt
from django.contrib.sites.models import Site
import mock

from django_comment_common.models import ForumsConfig
from django_comment_common.signals import comment_created
from edx_ace.recipient import Recipient
from lms.djangoapps.discussion.config.waffle import waffle, FORUM_RESPONSE_NOTIFICATIONS
from lms.djangoapps.discussion.tasks import ResponseNotification
from openedx.core.djangoapps.content.course_overviews.tests.factories import CourseOverviewFactory
from openedx.core.djangoapps.schedules.template_context import get_base_template_context
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase


def make_mock_responder(*thread_ids):
    def mock_response(*args, **kwargs):
        collection = [
            {'id': thread_id} for thread_id in thread_ids
        ]
        data = {
            'collection': collection,
            'page': 1,
            'num_pages': 1,
            'thread_count': len(collection)
        }
        return mock.Mock(status_code=200, text=json.dumps(data), json=mock.Mock(return_value=data))
    return mock_response


@ddt.ddt
class TaskTestCase(ModuleStoreTestCase):

    @mock.patch.dict("django.conf.settings.FEATURES", {"ENABLE_DISCUSSION_SERVICE": True})
    def setUp(self):
        super(TaskTestCase, self).setUp()

        self.discussion_id = 'dummy_discussion_id'
        self.course = CourseOverviewFactory.create(language='fr')

        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with mock.patch('student.models.cc.User.save'):

            self.thread_author = UserFactory(
                username='thread_author',
                password='password',
                email='email'
            )
            self.comment_author = UserFactory(
                username='comment_author',
                password='password',
                email='email'
            )

            CourseEnrollmentFactory(
                user=self.thread_author,
                course_id=self.course.id
            )
            CourseEnrollmentFactory(
                user=self.comment_author,
                course_id=self.course.id
            )

        config = ForumsConfig.current()
        config.enabled = True
        config.save()

    @ddt.data(True, False)
    def test_send_discussion_email_notification(self, user_subscribed):
        with mock.patch('requests.request') as mock_request, mock.patch('edx_ace.ace.send') as mock_ace_send:
            if user_subscribed:
                mock_request.side_effect = make_mock_responder(self.discussion_id)
            else:
                mock_request.side_effect = make_mock_responder()

            now = datetime.utcnow()
            one_hour_ago = now - timedelta(hours=1)
            thread = mock.Mock(
                id=self.discussion_id,
                course_id=unicode(self.course.id),
                created_at=one_hour_ago,
                title='thread-title',
                user_id=self.thread_author.id,
                username=self.thread_author.username
            )
            comment = mock.Mock(
                id='comment-id',
                body='comment-body',
                created_at=now,
                thread=thread,
                user_id=self.comment_author.id,
                username=self.comment_author.username
            )
            user = mock.Mock()

            with waffle().override(FORUM_RESPONSE_NOTIFICATIONS):
                comment_created.send(sender=None, user=user, post=comment)

            if user_subscribed:
                expected_message_context = get_base_template_context(Site.objects.get_current())
                expected_message_context.update({
                    'comment_author_id': self.comment_author.id,
                    'comment_body': 'comment-body',
                    'comment_created_at': now,
                    'comment_id': 'comment-id',
                    'comment_username': self.comment_author.username,
                    'course_id': self.course.id,
                    'thread_author_id': self.thread_author.id,
                    'thread_created_at': one_hour_ago,
                    'thread_id': self.discussion_id,
                    'thread_title': 'thread-title',
                    'thread_username': self.thread_author.username,
                    'post_link': None,
                    'unsubscribe_link': None
                })
                expected_recipient = Recipient(self.thread_author.username, self.thread_author.email)
                actual_message = mock_ace_send.call_args_list[0][0][0]
                self.assertEqual(expected_message_context, actual_message.context)
                self.assertEqual(expected_recipient, actual_message.recipient)
                self.assertEqual(self.course.language, actual_message.language)
            else:
                self.assertFalse(mock_ace_send.called)
