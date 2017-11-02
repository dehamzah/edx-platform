import json
import unittest
import pytest
import uuid

from django.conf import settings
from django.core.urlresolvers import reverse
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

from entitlements.tests.factories import CourseEntitlementFactory
from entitlements.models import CourseEntitlement
from openedx.core.lib.token_utils import JwtBuilder
from student.tests.factories import CourseEnrollmentFactory, UserFactory, TEST_PASSWORD


@unittest.skipUnless(settings.ROOT_URLCONF == 'lms.urls', 'Test only valid in lms')
class EntitlementsTest(ModuleStoreTestCase):
    """
    Entitlements API/View Tests
    """
    USERNAME = 'Bob'
    ENABLED_CACHES = ['default']
    COURSE_RUN_ID = 'some/great/course'

    def setUp(self):
        super(EntitlementsTest, self).setUp()
        self.user = UserFactory(is_staff=True)
        self.client.login(username=self.user.username, password=TEST_PASSWORD)
        self.course = CourseFactory.create(org='TestX', course='TS101', run='T1')
        # self.entitlements_url = '/api/entitlements/v1/entitlements/'
        self.entitlements_url = reverse('entitlements_api:api:entitlements-list')
        self.entitlements_uuid_path = 'entitlements_api:api:entitlements-list'
        self.course_uuid = str(uuid.uuid4())

    def _get_data_set(self, user):
        """
        Get a basic data set for an entitlement
        """
        return {
            "user": user.username,
            "mode": "verified",
            "course_uuid": self.course_uuid,
            "order_number": "EDX-1001"
        }

    def test_auth_required(self):
        self.client.logout()
        response = self.client.get(self.entitlements_url)
        assert response.status_code == 401

    def test_staff_user_required(self):
        not_staff_user = UserFactory()
        self.client.login(username=not_staff_user.username, password=UserFactory._DEFAULT_PASSWORD)
        response = self.client.get(self.entitlements_url)
        assert response.status_code == 403

    def test_add_entitlement_with_missing_data(self):
        entitlement_data_missing_parts = self._get_data_set(self.user)
        entitlement_data_missing_parts.pop('mode')
        entitlement_data_missing_parts.pop('course_uuid')

        response = self.client.post(
            self.entitlements_url,
            data=json.dumps(entitlement_data_missing_parts),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_add_entitlement(self):
        entitlement_data = self._get_data_set(self.user)

        response = self.client.post(
            self.entitlements_url,
            data=json.dumps(entitlement_data),
            content_type='application/json',
        )
        assert response.status_code == 201
        results = response.data
        assert results is not None

        course_entitlement = CourseEntitlement.objects.get(
            user=self.user,
            course_uuid=self.course_uuid
        )

        self.assertIsNotNone(course_entitlement)
        self.assertEqual(results['uuid'], str(course_entitlement.uuid))
        self.assertEqual(str(course_entitlement.course_uuid), self.course_uuid)
        self.assertEqual(course_entitlement.enrollment_course_run, None)
        self.assertEqual(course_entitlement.mode, 'verified')
        self.assertIsNotNone(course_entitlement.created)
        self.assertTrue(course_entitlement.user, self.user)

    def test_get_entitlements(self):
        CourseEntitlementFactory.create(user=self.user, order_number='TESTX-1001')
        CourseEntitlementFactory.create(user=self.user, order_number='TESTX-1002')

        response = self.client.get(
            self.entitlements_url,
            content_type='application/json',
        )
        assert response.status_code == 200

        results = response.data.get('results', [])
        assert len(results) == 2

    def test_get_entitlement_by_uuid(self):

        uuid1 = CourseEntitlementFactory.create(user=self.user, order_number='TESTX-1001').uuid
        CourseEntitlementFactory.create(user=self.user, order_number='TESTX-1002')
        url = '{}{}/'.format(self.entitlements_url, str(uuid1))
        # url = reverse(self.entitlements_uuid_path, args=[str(uuid1)])

        response = self.client.get(
            url,
            content_type='application/json',
        )
        assert response.status_code == 200

        results = response.data
        assert results['uuid'] == str(uuid1)

    def test_delete_and_revoke_entitlement(self):
        uuid1 = CourseEntitlementFactory.create(user=self.user, order_number='TESTX-1001').uuid

        url = '{}{}/'.format(self.entitlements_url, str(uuid1))

        response = self.client.delete(
            url,
            content_type='application/json',
        )
        assert response.status_code == 204

        course_entitlement = CourseEntitlement.objects.get(
            uuid=uuid1
        )

        self.assertIsNotNone(course_entitlement.expired_at)

    def test_revoke_unenroll_entitlement(self):
        uuid1 = CourseEntitlementFactory.create(user=self.user, order_number='TESTX-1001').uuid

        url = '{}{}/'.format(self.entitlements_url, str(uuid1))

        enrollment = CourseEnrollmentFactory.create(user=self.user, course_id=self.course.id)

        course_entitlement = CourseEntitlement.objects.get(
            uuid=uuid1
        )

        course_entitlement.enrollment_course_run = enrollment
        course_entitlement.save()

        assert course_entitlement.enrollment_course_run is not None

        response = self.client.delete(
            url,
            content_type='application/json',
        )
        assert response.status_code == 204

        course_entitlement = CourseEntitlement.objects.get(
            uuid=uuid1
        )
        assert course_entitlement.expired_at is not None
        assert course_entitlement.enrollment_course_run is None
