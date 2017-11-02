import factory
import uuid

from entitlements.models import CourseEntitlement
from student.tests.factories import UserFactory


class CourseEntitlementFactory(factory.django.DjangoModelFactory):
    class Meta(object):
        model = CourseEntitlement

    course_uuid = uuid.uuid4()
    mode = 'verified'
    user = factory.SubFactory(UserFactory)
    order_number = 'TESTX-1000'
