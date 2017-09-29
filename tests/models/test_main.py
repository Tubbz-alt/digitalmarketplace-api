from datetime import datetime, timedelta

import mock
import pytest
from nose.tools import assert_equal, assert_raises
from sqlalchemy.exc import IntegrityError

from app import db, create_app
from app.models import (
    User, Lot, Framework, Service,
    Supplier, SupplierFramework, FrameworkAgreement,
    Brief, BriefResponse,
    ValidationError,
    BriefClarificationQuestion,
    DraftService,
    FrameworkLot,
    ContactInformation
)
from tests.bases import BaseApplicationTest
from tests.helpers import FixtureMixin


def test_should_not_return_password_on_user():
    app = create_app('test')
    now = datetime.utcnow()
    user = User(
        email_address='email@digital.gov.uk',
        name='name',
        role='buyer',
        password='password',
        active=True,
        failed_login_count=0,
        created_at=now,
        updated_at=now,
        password_changed_at=now
    )

    with app.app_context():
        assert_equal(user.serialize()['emailAddress'], "email@digital.gov.uk")
        assert_equal(user.serialize()['name'], "name")
        assert_equal(user.serialize()['role'], "buyer")
        assert_equal('password' in user.serialize(), False)


def test_framework_should_not_accept_invalid_status():
    app = create_app('test')
    with app.app_context(), assert_raises(ValidationError):
        f = Framework(
            name='foo',
            slug='foo',
            framework='g-cloud',
            status='invalid',
        )
        db.session.add(f)
        db.session.commit()


def test_framework_should_accept_valid_statuses():
    app = create_app('test')
    with app.app_context():
        for i, status in enumerate(Framework.STATUSES):
            f = Framework(
                name='foo',
                slug='foo-{}'.format(i),
                framework='g-cloud',
                status=status,
            )
            db.session.add(f)
            db.session.commit()


class TestBriefs(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestBriefs, self).setup()
        with self.app.app_context():
            self.framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.lot = self.framework.get_lot('digital-outcomes')

    def test_create_a_new_brief(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot)
            db.session.add(brief)
            db.session.commit()

            assert isinstance(brief.created_at, datetime)
            assert isinstance(brief.updated_at, datetime)
            assert brief.id is not None
            assert brief.data == dict()
            assert brief.is_a_copy is False

    def test_updating_a_brief_updates_dates(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot)
            db.session.add(brief)
            db.session.commit()

            updated_at = brief.updated_at
            created_at = brief.created_at

            brief.data = {'foo': 'bar'}
            db.session.add(brief)
            db.session.commit()

            assert brief.created_at == created_at
            assert brief.updated_at > updated_at

    def test_update_from_json(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot)
            db.session.add(brief)
            db.session.commit()

            updated_at = brief.updated_at
            created_at = brief.created_at

            brief.update_from_json({"foo": "bar"})
            db.session.add(brief)
            db.session.commit()

            assert brief.created_at == created_at
            assert brief.updated_at > updated_at
            assert brief.data == {'foo': 'bar'}

    def test_foreign_fields_stripped_from_brief_data(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)
        brief.data = {
            'frameworkSlug': 'test',
            'frameworkName': 'test',
            'lot': 'test',
            'lotName': 'test',
            'title': 'test',
        }

        assert brief.data == {'title': 'test'}

    def test_nulls_are_stripped_from_brief_data(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)
        brief.data = {'foo': 'bar', 'bar': None}

        assert brief.data == {'foo': 'bar'}

    def test_whitespace_values_are_stripped_from_brief_data(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)
        brief.data = {'foo': ' bar ', 'bar': '', 'other': '  '}

        assert brief.data == {'foo': 'bar', 'bar': '', 'other': ''}

    def test_applications_closed_at_is_none_for_drafts(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)

        assert brief.applications_closed_at is None

    def test_closing_dates_are_set_with_published_at_when_no_requirements_length(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot,
                      published_at=datetime(2016, 3, 3, 12, 30, 1, 2))

        assert brief.applications_closed_at == datetime(2016, 3, 17, 23, 59, 59)
        assert brief.clarification_questions_closed_at == datetime(2016, 3, 10, 23, 59, 59)
        assert brief.clarification_questions_published_by == datetime(2016, 3, 16, 23, 59, 59)

    def test_closing_dates_are_set_with_published_at_when_requirements_length_is_two_weeks(self):
        brief = Brief(data={'requirementsLength': '2 weeks'}, framework=self.framework, lot=self.lot,
                      published_at=datetime(2016, 3, 3, 12, 30, 1, 2))

        assert brief.applications_closed_at == datetime(2016, 3, 17, 23, 59, 59)
        assert brief.clarification_questions_closed_at == datetime(2016, 3, 10, 23, 59, 59)
        assert brief.clarification_questions_published_by == datetime(2016, 3, 16, 23, 59, 59)

    def test_closing_dates_are_set_with_published_at_when_requirements_length_is_one_week(self):
        brief = Brief(data={'requirementsLength': '1 week'}, framework=self.framework, lot=self.lot,
                      published_at=datetime(2016, 3, 3, 12, 30, 1, 2))

        assert brief.applications_closed_at == datetime(2016, 3, 10, 23, 59, 59)
        assert brief.clarification_questions_closed_at == datetime(2016, 3, 7, 23, 59, 59)
        assert brief.clarification_questions_published_by == datetime(2016, 3, 9, 23, 59, 59)

    def test_buyer_users_can_be_added_to_a_brief(self):
        with self.app.app_context():
            self.setup_dummy_user(role='buyer')

            brief = Brief(data={}, framework=self.framework, lot=self.lot,
                          users=User.query.all())

            assert len(brief.users) == 1

    def test_non_buyer_users_cannot_be_added_to_a_brief(self):
        with self.app.app_context():
            self.setup_dummy_user(role='admin')

            with pytest.raises(ValidationError):
                Brief(data={}, framework=self.framework, lot=self.lot,
                      users=User.query.all())

    def test_brief_lot_must_be_associated_to_the_framework(self):
        with self.app.app_context():
            other_framework = Framework.query.filter(Framework.slug == 'g-cloud-7').first()

            brief = Brief(data={}, framework=other_framework, lot=self.lot)
            db.session.add(brief)
            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_brief_lot_must_require_briefs(self):
        with self.app.app_context():
            with pytest.raises(ValidationError):
                Brief(data={},
                      framework=self.framework,
                      lot=self.framework.get_lot('user-research-studios'))

    def test_cannot_update_lot_by_id(self):
        with self.app.app_context():
            with pytest.raises(ValidationError):
                Brief(data={},
                      framework=self.framework,
                      lot_id=self.framework.get_lot('user-research-studios').id)

    def test_add_brief_clarification_question(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot, status="live")
            db.session.add(brief)
            db.session.commit()

            brief.add_clarification_question(
                "How do you expect to deliver this?",
                "By the power of Grayskull")
            db.session.commit()

            assert len(brief.clarification_questions) == 1
            assert len(BriefClarificationQuestion.query.filter(
                BriefClarificationQuestion._brief_id == brief.id
            ).all()) == 1

    def test_new_clarification_questions_get_added_to_the_end(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot, status="live")
            db.session.add(brief)
            brief.add_clarification_question("How?", "This")
            brief.add_clarification_question("When", "Then")
            db.session.commit()

            assert brief.clarification_questions[0].question == "How?"
            assert brief.clarification_questions[1].question == "When"


class TestBriefStatuses(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestBriefStatuses, self).setup()
        with self.app.app_context():
            self.framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.lot = self.framework.get_lot('digital-outcomes')

    def test_status_defaults_to_draft(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)
        assert brief.status == 'draft'

    def test_live_status_for_briefs_with_published_at(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime.utcnow())
        assert brief.status == 'live'

    def test_closed_status_for_a_brief_with_passed_close_date(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot,
                      published_at=datetime.utcnow() - timedelta(days=1000))

        assert brief.status == 'closed'
        assert brief.clarification_questions_are_closed
        assert brief.applications_closed_at < datetime.utcnow()

    def test_awarded_status_for_a_brief_with_an_awarded_brief_response(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            brief_response = BriefResponse(brief=brief, supplier_id=0, submitted_at=datetime.utcnow(), data={})
            brief_response.award_details = {"confirmed": "details"}
            brief_response.awarded_at = datetime(2016, 12, 12, 1, 1, 1)
            db.session.add_all([brief, brief_response])
            db.session.commit()

            brief = Brief.query.get(brief.id)
            assert brief.status == 'awarded'

    def test_publishing_a_brief_sets_published_at(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)
        assert brief.published_at is None

        brief.status = 'live'
        assert not brief.clarification_questions_are_closed
        assert isinstance(brief.published_at, datetime)

    def test_withdrawing_a_brief_sets_withdrawn_at(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime.utcnow())
        assert brief.withdrawn_at is None

        brief.status = 'withdrawn'
        assert isinstance(brief.withdrawn_at, datetime)

    def test_cancelling_a_brief_sets_cancelled_at(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
        assert brief.cancelled_at is None

        brief.status = 'cancelled'
        assert isinstance(brief.cancelled_at, datetime)

    def test_unsuccessfulling_a_brief_sets_unsuccessful_at(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
        assert brief.unsuccessful_at is None

        brief.status = 'unsuccessful'
        assert isinstance(brief.unsuccessful_at, datetime)

    def test_can_set_draft_brief_to_the_same_status(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)
        brief.status = 'draft'

    def test_can_set_live_brief_to_withdrawn(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime.utcnow())
        brief.status = 'withdrawn'

        assert brief.published_at is not None
        assert brief.withdrawn_at is not None

    def test_cannot_set_any_brief_to_an_invalid_status(self):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)

        with pytest.raises(ValidationError) as e:
            brief.status = 'invalid'
        assert e.value.message == "Cannot change brief status from 'draft' to 'invalid'"

    @pytest.mark.parametrize('status', ['draft', 'closed', 'awarded', 'cancelled', 'unsuccessful'])
    def test_cannot_set_live_brief_to_non_withdrawn_status(self, status):
        brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime.utcnow())

        with pytest.raises(ValidationError) as e:
            brief.status = status
        assert e.value.message == "Cannot change brief status from 'live' to '{}'".format(status)

    @pytest.mark.parametrize('status', ['withdrawn', 'closed', 'awarded', 'cancelled', 'unsuccessful'])
    def test_cannot_set_draft_brief_to_withdrawn_closed_awarded_cancelled_or_unsuccessful(self, status):
        brief = Brief(data={}, framework=self.framework, lot=self.lot)

        with pytest.raises(ValidationError) as e:
            brief.status = status
        assert e.value.message == "Cannot change brief status from 'draft' to '{}'".format(status)

    def test_cannot_change_status_of_withdrawn_brief(self):
        brief = Brief(
            data={}, framework=self.framework, lot=self.lot,
            published_at=datetime.utcnow() - timedelta(days=1), withdrawn_at=datetime.utcnow()
        )

        for status in ['draft', 'live', 'closed', 'awarded', 'cancelled', 'unsuccessful']:
            with pytest.raises(ValidationError) as e:
                brief.status = status
            assert e.value.message == "Cannot change brief status from 'withdrawn' to '{}'".format(status)

    def test_status_order_sorts_briefs_by_search_result_status_ordering(self):
        with self.app.app_context():
            draft_brief = Brief(data={}, framework=self.framework, lot=self.lot)
            live_brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime.utcnow())
            withdrawn_brief = Brief(
                data={}, framework=self.framework, lot=self.lot,
                published_at=datetime.utcnow() - timedelta(days=1), withdrawn_at=datetime.utcnow()
            )
            closed_brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            cancelled_brief = Brief(
                data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1),
                cancelled_at=datetime(2000, 2, 2)
            )
            unsuccessful_brief = Brief(
                data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1),
                unsuccessful_at=datetime(2000, 2, 2)
            )

            awarded_brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            self.setup_dummy_suppliers(1)
            brief_response = BriefResponse(
                brief=awarded_brief, data={}, supplier_id=0, submitted_at=datetime(2000, 2, 1),
                award_details={'pending': True}
            )
            db.session.add_all([
                draft_brief, live_brief, withdrawn_brief, closed_brief, awarded_brief, brief_response,
                cancelled_brief, unsuccessful_brief
            ])
            db.session.commit()
            # award the BriefResponse
            brief_response.awarded_at = datetime(2001, 1, 1)
            db.session.add(brief_response)
            db.session.commit()

            expected_result = [
                live_brief.status, closed_brief.status, awarded_brief.status,
                cancelled_brief.status, unsuccessful_brief.status,
                draft_brief.status, withdrawn_brief.status
            ]
            query_result = [
                q.status for q in Brief.query.order_by(Brief.status_order, Brief.published_at.desc(), Brief.id)
            ]

            assert query_result == expected_result


class TestBriefQueries(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestBriefQueries, self).setup()
        with self.app.app_context():
            self.framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.lot = self.framework.get_lot('digital-outcomes')

    def test_query_draft_brief(self):
        with self.app.app_context():
            db.session.add(Brief(data={}, framework=self.framework, lot=self.lot))
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'draft').count() == 1
            assert Brief.query.filter(Brief.status == 'live').count() == 0
            assert Brief.query.filter(Brief.status == 'withdrawn').count() == 0
            assert Brief.query.filter(Brief.status == 'closed').count() == 0
            assert Brief.query.filter(Brief.status == 'awarded').count() == 0
            assert Brief.query.filter(Brief.status == 'cancelled').count() == 0
            assert Brief.query.filter(Brief.status == 'unsuccessful').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'draft'

    def test_query_live_brief(self):
        with self.app.app_context():
            db.session.add(Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime.utcnow()))
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'draft').count() == 0
            assert Brief.query.filter(Brief.status == 'live').count() == 1
            assert Brief.query.filter(Brief.status == 'withdrawn').count() == 0
            assert Brief.query.filter(Brief.status == 'closed').count() == 0
            assert Brief.query.filter(Brief.status == 'awarded').count() == 0
            assert Brief.query.filter(Brief.status == 'cancelled').count() == 0
            assert Brief.query.filter(Brief.status == 'unsuccessful').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'live'

    def test_query_withdrawn_brief(self):
        with self.app.app_context():
            db.session.add(Brief(
                data={}, framework=self.framework, lot=self.lot,
                published_at=datetime.utcnow() - timedelta(days=1), withdrawn_at=datetime.utcnow()
            ))
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'draft').count() == 0
            assert Brief.query.filter(Brief.status == 'live').count() == 0
            assert Brief.query.filter(Brief.status == 'withdrawn').count() == 1
            assert Brief.query.filter(Brief.status == 'closed').count() == 0
            assert Brief.query.filter(Brief.status == 'awarded').count() == 0
            assert Brief.query.filter(Brief.status == 'cancelled').count() == 0
            assert Brief.query.filter(Brief.status == 'unsuccessful').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'withdrawn'

    def test_query_closed_brief(self):
        with self.app.app_context():
            db.session.add(Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1)))
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'draft').count() == 0
            assert Brief.query.filter(Brief.status == 'live').count() == 0
            assert Brief.query.filter(Brief.status == 'withdrawn').count() == 0
            assert Brief.query.filter(Brief.status == 'closed').count() == 1
            assert Brief.query.filter(Brief.status == 'awarded').count() == 0
            assert Brief.query.filter(Brief.status == 'cancelled').count() == 0
            assert Brief.query.filter(Brief.status == 'unsuccessful').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'closed'

    def test_query_cancelled_brief(self):
        with self.app.app_context():
            db.session.add(
                Brief(
                    data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1),
                    cancelled_at=datetime(2000, 2, 2)
                )
            )
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'draft').count() == 0
            assert Brief.query.filter(Brief.status == 'live').count() == 0
            assert Brief.query.filter(Brief.status == 'withdrawn').count() == 0
            assert Brief.query.filter(Brief.status == 'closed').count() == 0
            assert Brief.query.filter(Brief.status == 'awarded').count() == 0
            assert Brief.query.filter(Brief.status == 'cancelled').count() == 1
            assert Brief.query.filter(Brief.status == 'unsuccessful').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'cancelled'

    def test_query_unsuccessful_brief(self):
        with self.app.app_context():
            db.session.add(
                Brief(
                    data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1),
                    unsuccessful_at=datetime(2000, 2, 2)
                )
            )
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'draft').count() == 0
            assert Brief.query.filter(Brief.status == 'live').count() == 0
            assert Brief.query.filter(Brief.status == 'withdrawn').count() == 0
            assert Brief.query.filter(Brief.status == 'closed').count() == 0
            assert Brief.query.filter(Brief.status == 'awarded').count() == 0
            assert Brief.query.filter(Brief.status == 'cancelled').count() == 0
            assert Brief.query.filter(Brief.status == 'unsuccessful').count() == 1

            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'unsuccessful'

    def test_query_awarded_brief(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            self.setup_dummy_suppliers(1)
            brief_response = BriefResponse(
                brief=brief, data={}, supplier_id=0, submitted_at=datetime(2000, 2, 1),
                award_details={'pending': True}
            )
            db.session.add_all([brief, brief_response])
            db.session.commit()
            # award the BriefResponse
            brief_response.awarded_at = datetime(2001, 1, 1)
            db.session.add(brief_response)
            db.session.commit()

            assert Brief.query.filter(Brief.status == 'awarded').count() == 1
            # Check python implementation gives same result as the sql implementation
            assert Brief.query.all()[0].status == 'awarded'

    def test_query_brief_applications_closed_at_date_for_brief_with_no_requirements_length(self):
        with self.app.app_context():
            db.session.add(Brief(data={}, framework=self.framework, lot=self.lot,
                                 published_at=datetime(2016, 3, 3, 12, 30, 1, 2)))
            db.session.commit()
            assert Brief.query.filter(Brief.applications_closed_at == datetime(2016, 3, 17, 23, 59, 59)).count() == 1

    def test_query_brief_applications_closed_at_date_for_one_week_brief(self):
        with self.app.app_context():
            db.session.add(Brief(data={'requirementsLength': '1 week'}, framework=self.framework, lot=self.lot,
                                 published_at=datetime(2016, 3, 3, 12, 30, 1, 2)))
            db.session.commit()
            assert Brief.query.filter(Brief.applications_closed_at == datetime(2016, 3, 10, 23, 59, 59)).count() == 1

    def test_query_brief_applications_closed_at_date_for_two_week_brief(self):
        with self.app.app_context():
            db.session.add(Brief(data={'requirementsLength': '2 weeks'}, framework=self.framework, lot=self.lot,
                                 published_at=datetime(2016, 3, 3, 12, 30, 1, 2)))
            db.session.commit()
            assert Brief.query.filter(Brief.applications_closed_at == datetime(2016, 3, 17, 23, 59, 59)).count() == 1

    def test_query_brief_applications_closed_at_date_for_mix_of_brief_lengths(self):
        with self.app.app_context():
            db.session.add(Brief(data={'requirementsLength': '1 week'}, framework=self.framework, lot=self.lot,
                                 published_at=datetime(2016, 3, 10, 12, 30, 1, 2)))
            db.session.add(Brief(data={'requirementsLength': '2 weeks'}, framework=self.framework, lot=self.lot,
                                 published_at=datetime(2016, 3, 3, 12, 30, 1, 2)))
            db.session.add(Brief(data={}, framework=self.framework, lot=self.lot,
                                 published_at=datetime(2016, 3, 3, 12, 30, 1, 2)))
            db.session.commit()
            assert Brief.query.filter(Brief.applications_closed_at == datetime(2016, 3, 17, 23, 59, 59)).count() == 3


class TestAwardedBriefs(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestAwardedBriefs, self).setup()
        with self.app.app_context():
            self.framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.lot = self.framework.get_lot('digital-outcomes')

    def _setup_brief_and_awarded_brief_response(self, context, awarded_at=True, pending=True):
        with context:
            self.setup_dummy_suppliers(1)
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            brief_response = BriefResponse(
                brief=brief,
                supplier_id=0,
                data={'boo': 'far'},
                created_at=datetime.utcnow(),
                submitted_at=datetime.utcnow()
            )
            db.session.add_all([brief, brief_response])
            db.session.commit()
            brief_response.award_details = {'pending': True} if pending else {'confirmed': 'details'}
            if awarded_at:
                brief_response.awarded_at = datetime(2016, 1, 1)
            db.session.add(brief_response)
            db.session.commit()
            return brief.id, brief_response.id

    def test_awarded_brief_response_when_there_is_an_award(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            brief_response1 = BriefResponse(brief=brief, supplier_id=0, submitted_at=datetime.utcnow(), data={})
            brief_response2 = BriefResponse(brief=brief, supplier_id=0, submitted_at=datetime.utcnow(), data={})
            brief_response2.award_details = {"confirmed": "details"}
            brief_response2.awarded_at = datetime(2016, 12, 12, 1, 1, 1)
            db.session.add_all([brief, brief_response1, brief_response2])
            db.session.commit()

            brief = Brief.query.get(brief.id)
            assert brief.awarded_brief_response.id == brief_response2.id

    def test_no_awarded_brief_response_if_brief_responses_but_no_award(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            brief_response1 = BriefResponse(brief=brief, supplier_id=0, submitted_at=datetime.utcnow(), data={})
            brief_response2 = BriefResponse(brief=brief, supplier_id=0, submitted_at=datetime.utcnow(), data={})
            db.session.add_all([brief, brief_response1, brief_response2])
            db.session.commit()

            brief = Brief.query.get(brief.id)
            assert brief.awarded_brief_response is None

    def test_no_awarded_brief_response_if_no_brief_responses(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            db.session.add(brief)
            db.session.commit()

            brief = Brief.query.get(brief.id)
            assert brief.awarded_brief_response is None

    def test_brief_serialize_includes_awarded_brief_response_id_if_overall_status_awarded(self):
        with self.app.app_context() as context:
            brief_id, brief_response_id = self._setup_brief_and_awarded_brief_response(context, pending=False)
            brief = Brief.query.get(brief_id)
            assert brief.status == 'awarded'
            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief.serialize().get('awardedBriefResponseId') == brief_response_id

    def test_brief_serialize_does_not_include_awarded_brief_response_if_award_is_pending(self):
        with self.app.app_context() as context:
            brief_id, brief_response_id = self._setup_brief_and_awarded_brief_response(context, awarded_at=False)
            brief = Brief.query.get(brief_id)
            assert brief.status == 'closed'
            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief.serialize().get('awardedBriefResponseId') is None

    def test_brief_serialize_does_not_include_awarded_brief_response_if_no_awarded_brief_response(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot, published_at=datetime(2000, 1, 1))
            db.session.add(brief)
            db.session.commit()
            brief = Brief.query.get(brief.id)
            assert brief.status == 'closed'
            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief.serialize().get('awardedBriefResponseId') is None


class TestCopyBrief(BaseApplicationTest, FixtureMixin):

    def setup(self, *args, **kwargs):
        super(TestCopyBrief, self).setup(*args, **kwargs)
        self.app.app_context().push()
        self.setup_dummy_user(role='buyer')
        self.framework = Framework.query.filter(
            Framework.slug == 'digital-outcomes-and-specialists',
        ).one()
        self.lot = self.framework.get_lot('digital-outcomes')

        self.brief = Brief(
            data={'title': 'my title'},
            framework=self.framework,
            lot=self.lot,
            users=User.query.all(),
            status="live"
        )
        db.session.add(self.brief)
        question = BriefClarificationQuestion(
            brief=self.brief,
            question='hi',
            answer='there',
        )
        db.session.add(question)
        db.session.commit()

    def test_copy_brief(self, live_dos_framework):
        copy = self.brief.copy()

        assert copy.framework == self.brief.framework
        assert copy.lot == self.brief.lot
        assert copy.users == self.brief.users
        assert copy.is_a_copy is True

    def test_clarification_questions_not_copied(self, live_dos_framework):
        copy = self.brief.copy()

        assert not copy.clarification_questions

    def test_copied_brief_status_is_draft(self, live_dos_framework):
        copy = self.brief.copy()

        assert copy.status == 'draft'

    def test_brief_title_under_96_chars_adds_copy_string(self, live_dos_framework):
        title = 't' * 95
        self.brief.data['title'] = title
        copy = self.brief.copy()

        assert copy.data['title'] == title + ' copy'

    def test_brief_title_over_95_chars_does_not_add_copy_string(self, live_dos_framework):
        title = 't' * 96
        self.brief.data['title'] = title
        copy = self.brief.copy()

        assert copy.data['title'] == title

    def test_fields_to_remove_are_removed_on_copy(self, live_dos_framework):
        self.brief.data = {
            "other key": "to be kept",
            "startDate": "21-4-2016",
            "questionAndAnswerSessionDetails": "details",
            "researchDates": "some date"
        }
        copy = self.brief.copy()
        assert copy.data == {"other key": "to be kept"}

    def test_copy_is_put_on_live_framework(self, expired_dos_framework, live_dos2_framework):
        """If brief is on framework which is not live its copy chould be moved to the live framework."""
        expired_framework = Framework.query.filter(Framework.id == expired_dos_framework['id']).first()
        live_framework = Framework.query.filter(Framework.id == live_dos2_framework['id']).first()
        self.brief.framework = expired_framework

        copy = self.brief.copy()

        assert copy.framework == live_framework


class TestBriefResponses(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestBriefResponses, self).setup()
        with self.app.app_context():
            framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.brief_title = 'My Test Brief Title'
            self.brief = self._create_brief()
            db.session.add(self.brief)
            db.session.commit()
            self.brief_id = self.brief.id

            self.setup_dummy_suppliers(1)
            self.supplier = Supplier.query.filter(Supplier.supplier_id == 0).first()
            supplier_framework = SupplierFramework(
                supplier=self.supplier,
                framework=framework,
                declaration={'organisationSize': 'small'}
            )
            db.session.add(supplier_framework)
            db.session.commit()

    def _create_brief(self, published_at=datetime(2016, 3, 3, 12, 30, 1, 3)):
        framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
        lot = framework.get_lot('digital-outcomes')
        return Brief(
            data={'title': self.brief_title, 'requirementsLength': '1 week'},
            framework=framework,
            lot=lot,
            published_at=published_at
        )

    def test_create_a_new_brief_response(self):
        with self.app.app_context():
            brief_response = BriefResponse(data={}, brief=self.brief, supplier=self.supplier)
            db.session.add(brief_response)
            db.session.commit()

            assert brief_response.id is not None
            assert brief_response.supplier_id == 0
            assert brief_response.brief_id == self.brief.id
            assert isinstance(brief_response.created_at, datetime)
            assert brief_response.data == {}

    def test_foreign_fields_are_removed_from_brief_response_data(self):
        brief_response = BriefResponse(data={})
        brief_response.data = {'foo': 'bar', 'briefId': 5, 'supplierId': 100}

        assert brief_response.data == {'foo': 'bar'}

    def test_nulls_are_removed_from_brief_response_data(self):
        brief_response = BriefResponse(data={})
        brief_response.data = {'foo': 'bar', 'bar': None}

        assert brief_response.data == {'foo': 'bar'}

    def test_whitespace_is_stripped_from_brief_response_data(self):
        brief_response = BriefResponse(data={})
        brief_response.data = {'foo': ' bar ', 'bar': ['', '  foo', {'evidence': ' some '}]}

        assert brief_response.data == {'foo': 'bar', 'bar': ['foo', {'evidence': 'some'}]}

    def test_submitted_status_for_brief_response_with_submitted_at(self):
        brief_response = BriefResponse(created_at=datetime.utcnow(), submitted_at=datetime.utcnow())
        assert brief_response.status == 'submitted'

    def test_draft_status_for_brief_response_with_no_submitted_at(self):
        brief_response = BriefResponse(created_at=datetime.utcnow())
        assert brief_response.status == 'draft'

    def test_awarded_status_for_brief_response_with_awarded_at_datestamp(self):
        with self.app.app_context():
            brief = Brief.query.get(self.brief_id)
            brief_response = BriefResponse(
                brief=brief,
                data={},
                supplier_id=0,
                submitted_at=datetime.utcnow(),
                award_details={'pending': True},
            )
            brief_response.award_details = {'confirmed': 'details'},
            brief_response.awarded_at = datetime(2016, 1, 1)
            db.session.add(brief_response)
            db.session.commit()

            assert BriefResponse.query.filter(BriefResponse.status == 'awarded').count() == 1

    def test_awarded_status_for_pending_awarded_brief_response(self):
        with self.app.app_context():
            brief = Brief.query.get(self.brief_id)
            brief_response = BriefResponse(
                brief=brief,
                data={},
                supplier_id=0,
                submitted_at=datetime.utcnow(),
                award_details={'pending': True}
            )
            db.session.add(brief_response)
            db.session.commit()

            assert BriefResponse.query.filter(BriefResponse.status == 'pending-awarded').count() == 1

    def test_query_draft_brief_response(self):
        with self.app.app_context():
            db.session.add(BriefResponse(brief_id=self.brief_id, supplier_id=0, data={}))
            db.session.commit()

            assert BriefResponse.query.filter(BriefResponse.status == 'draft').count() == 1
            assert BriefResponse.query.filter(BriefResponse.status == 'submitted').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert BriefResponse.query.all()[0].status == 'draft'

    def test_query_submitted_brief_response(self):
        with self.app.app_context():
            db.session.add(BriefResponse(
                brief_id=self.brief_id, supplier_id=0, submitted_at=datetime.utcnow(),
                data={})
            )
            db.session.commit()

            assert BriefResponse.query.filter(BriefResponse.status == 'submitted').count() == 1
            assert BriefResponse.query.filter(BriefResponse.status == 'draft').count() == 0

            # Check python implementation gives same result as the sql implementation
            assert BriefResponse.query.all()[0].status == 'submitted'

    def test_brief_response_can_be_serialized(self):
        with self.app.app_context():
            brief_response = BriefResponse(
                data={'foo': 'bar'}, brief=self.brief, supplier=self.supplier, submitted_at=datetime(2016, 9, 28)
            )
            db.session.add(brief_response)
            db.session.commit()

            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief_response.serialize() == {
                    'id': brief_response.id,
                    'brief': {
                        'applicationsClosedAt': '2016-03-10T23:59:59.000000Z',
                        'id': self.brief.id,
                        'status': self.brief.status,
                        'title': self.brief_title,
                        'frameworkSlug': self.brief.framework.slug
                    },
                    'briefId': self.brief.id,
                    'supplierId': 0,
                    'supplierName': 'Supplier 0',
                    'supplierOrganisationSize': 'small',
                    'createdAt': mock.ANY,
                    'submittedAt': '2016-09-28T00:00:00.000000Z',
                    'status': 'submitted',
                    'foo': 'bar',
                    'links': {
                        'self': (('main.get_brief_response',), {'brief_response_id': brief_response.id}),
                        'brief': (('main.get_brief',), {'brief_id': self.brief.id}),
                        'supplier': (('main.get_supplier',), {'supplier_id': 0}),
                    }
                }

    def test_brief_response_can_be_serialized_with_no_submitted_at_time(self):
        with self.app.app_context():
            brief_response = BriefResponse(
                data={'foo': 'bar'}, brief=self.brief, supplier=self.supplier
            )
            db.session.add(brief_response)
            db.session.commit()

            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief_response.serialize() == {
                    'id': brief_response.id,
                    'briefId': self.brief.id,
                    'brief': {
                        'applicationsClosedAt': '2016-03-10T23:59:59.000000Z',
                        'id': self.brief.id,
                        'status': self.brief.status,
                        'title': self.brief_title,
                        'frameworkSlug': self.brief.framework.slug
                    },
                    'supplierId': 0,
                    'supplierName': 'Supplier 0',
                    'supplierOrganisationSize': 'small',
                    'createdAt': mock.ANY,
                    'status': 'draft',
                    'foo': 'bar',
                    'links': {
                        'self': (('main.get_brief_response',), {'brief_response_id': brief_response.id}),
                        'brief': (('main.get_brief',), {'brief_id': self.brief.id}),
                        'supplier': (('main.get_supplier',), {'supplier_id': 0}),
                    }
                }

    def test_brief_response_serialization_includes_award_details_if_status_awarded(self):
        with self.app.app_context():
            brief_response = BriefResponse(
                data={'foo': 'bar'}, brief=self.brief, supplier=self.supplier, submitted_at=datetime(2016, 9, 28)
            )
            db.session.add(brief_response)
            db.session.commit()
            brief_response.award_details = {
                "awardedContractStartDate": "2020-12-31",
                "awardedContractValue": "99.95"
            }
            brief_response.awarded_at = datetime(2016, 1, 1)
            db.session.add(brief_response)
            db.session.commit()

            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief_response.serialize()['awardDetails'] == {
                    "awardedContractStartDate": "2020-12-31",
                    "awardedContractValue": "99.95"
                }

    def test_brief_response_serialization_includes_pending_flag_if_status_pending_awarded(self):
        with self.app.app_context():
            brief_response = BriefResponse(
                data={'foo': 'bar'}, brief=self.brief, supplier=self.supplier, submitted_at=datetime(2016, 9, 28)
            )
            db.session.add(brief_response)
            db.session.commit()
            brief_response.award_details = {"pending": True}
            db.session.add(brief_response)
            db.session.commit()

            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert brief_response.serialize()['awardDetails'] == {"pending": True}

    def test_brief_response_awarded_at_index_raises_integrity_error_on_more_than_one_award_per_brief(self):
        timestamp = datetime(2016, 12, 31, 12, 1, 2, 3)
        with self.app.app_context():
            brief = Brief.query.get(self.brief_id)
            brief_response1 = BriefResponse(
                data={}, brief=brief, supplier=self.supplier, submitted_at=datetime.utcnow(),
                award_details={'pending': True},
            )
            brief_response1.award_details = {'confirmed': 'details'},
            brief_response1.awarded_at = timestamp
            brief_response2 = BriefResponse(
                data={}, brief=brief, supplier=self.supplier, submitted_at=datetime.utcnow(),
                award_details={'pending': True},
            )
            brief_response2.award_details = {'confirmed': 'details'},
            brief_response2.awarded_at = timestamp
            db.session.add_all([brief_response1, brief_response2])
            with pytest.raises(IntegrityError) as exc:
                db.session.commit()
            assert 'duplicate key value violates unique constraint' in str(exc.value)

    def test_brief_response_awarded_index_can_save_awards_for_unique_briefs(self):
        timestamp = datetime(2016, 12, 31, 12, 1, 2, 3)
        with self.app.app_context():
            brief = Brief.query.get(self.brief_id)
            brief2 = self._create_brief()
            db.session.add(brief2)
            brief_response1 = BriefResponse(
                data={}, brief=brief, supplier=self.supplier, submitted_at=datetime.utcnow(),
                award_details={'pending': True}
            )
            brief_response1.awarded_at = timestamp
            brief_response1.award_details = {'confirmed': 'details'}
            brief_response2 = BriefResponse(
                data={}, brief=brief, supplier=self.supplier, submitted_at=datetime.utcnow(),
                award_details={'pending': True}, awarded_at=None
            )
            brief_response3 = BriefResponse(
                data={}, brief=brief2, supplier=self.supplier, submitted_at=datetime.utcnow(),
                award_details={'pending': True}, awarded_at=None
            )
            brief_response4 = BriefResponse(
                data={}, brief=brief2, supplier=self.supplier, submitted_at=datetime.utcnow(),
                award_details={'pending': True}
            )
            brief_response4.awarded_at = timestamp
            brief_response4.award_details = {'confirmed': 'details'}

            db.session.add_all([brief_response1, brief_response2, brief_response3, brief_response4])
            db.session.commit()

            for b in [brief_response1, brief_response2, brief_response3, brief_response4]:
                assert b.id

    def test_brief_response_awarded_index_can_save_multiple_non_awarded_responses(self):
        with self.app.app_context():
            brief = Brief.query.get(self.brief_id)
            brief_response1 = BriefResponse(
                data={}, brief=brief, supplier=self.supplier, submitted_at=datetime.utcnow(), awarded_at=None
            )
            brief_response2 = BriefResponse(
                data={}, brief=brief, supplier=self.supplier, submitted_at=datetime.utcnow(), awarded_at=None
            )
            db.session.add_all([brief_response1, brief_response2])
            db.session.commit()

            for b in [brief_response1, brief_response2]:
                assert b.id

    def test_brief_response_awarded_index_sets_default_value(self):
        with self.app.app_context():
            brief_response = BriefResponse(data={}, brief=self.brief, supplier=self.supplier)
            db.session.add(brief_response)
            db.session.commit()

            assert brief_response.id
            assert brief_response.awarded_at is None

    def test_brief_response_can_not_be_awarded_if_brief_is_not_closed(self):
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            brief = self._create_brief(published_at=datetime.utcnow())
            brief_response = BriefResponse(data={}, brief=brief, supplier=self.supplier)
            db.session.add_all([brief, brief_response])
            db.session.commit()

            existing_brief_response = BriefResponse.query.get(brief_response.id)
            existing_brief_response.awarded_at = datetime(2016, 12, 31, 12, 1, 1)
            db.session.add(existing_brief_response)
            db.session.commit()

        assert 'Brief response can not be awarded if the brief is not closed' in e.value.message

    def test_brief_response_can_not_be_awarded_if_brief_response_has_not_been_submitted(self):
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            brief_response = BriefResponse(data={}, brief=self.brief, supplier=self.supplier)
            db.session.add(brief_response)
            db.session.commit()

            existing_brief_response = BriefResponse.query.get(brief_response.id)
            existing_brief_response.awarded_at = datetime(2016, 12, 31, 12, 1, 1)
            db.session.add(existing_brief_response)
            db.session.commit()

        assert 'Brief response can not be awarded if response has not been submitted' in e.value.message

    def test_can_remove_award_details_from_brief_response_if_brief_not_awarded(self):
        with self.app.app_context():
            brief_response = BriefResponse(
                data={}, brief=self.brief, supplier=self.supplier, submitted_at=datetime.utcnow()
            )
            db.session.add(brief_response)
            db.session.commit()
            # Pending award to this brief response
            brief_response.award_details = {'pending': True}
            db.session.add(brief_response)
            db.session.commit()
            # There's still time to change our minds...
            brief_response.award_details = {}
            db.session.add(brief_response)
            db.session.commit()

    def test_cannot_remove_award_from_brief_response_if_brief_awarded(self):
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            brief_response = BriefResponse(
                data={}, brief=self.brief, supplier=self.supplier, submitted_at=datetime.utcnow()
            )
            db.session.add(brief_response)
            db.session.commit()
            # Confirm award to this brief response
            brief_response.award_details = {'confirmed': 'details'}
            brief_response.awarded_at = datetime.utcnow()
            db.session.add(brief_response)
            db.session.commit()
            # We've changed our minds again but it's too late...
            brief_response.awarded_at = None

        assert 'Cannot remove or change award datestamp on previously awarded Brief Response' in e.value.message


class TestBriefClarificationQuestion(BaseApplicationTest):
    def setup(self):
        super(TestBriefClarificationQuestion, self).setup()
        with self.app.app_context():
            self.framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.lot = self.framework.get_lot('digital-outcomes')
            self.brief = Brief(data={}, framework=self.framework, lot=self.lot, status="live")
            db.session.add(self.brief)
            db.session.commit()

            # Reload objects after session commit
            self.framework = Framework.query.get(self.framework.id)
            self.lot = Lot.query.get(self.lot.id)
            self.brief = Brief.query.get(self.brief.id)

    def test_brief_must_be_live(self):
        with self.app.app_context():
            brief = Brief(data={}, framework=self.framework, lot=self.lot, status="draft")
            with pytest.raises(ValidationError) as e:
                BriefClarificationQuestion(brief=brief, question="Why?", answer="Because")

            assert str(e.value.message) == "Brief status must be 'live', not 'draft'"

    def test_cannot_update_brief_by_id(self):
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            BriefClarificationQuestion(brief_id=self.brief.id, question="Why?", answer="Because")

        assert str(e.value.message) == "Cannot update brief_id directly, use brief relationship"

    def test_published_at_is_set_on_creation(self):
        with self.app.app_context():
            question = BriefClarificationQuestion(
                brief=self.brief, question="Why?", answer="Because")

            db.session.add(question)
            db.session.commit()

            assert isinstance(question.published_at, datetime)

    def test_question_must_not_be_null(self):
        with self.app.app_context(), pytest.raises(IntegrityError):
            question = BriefClarificationQuestion(brief=self.brief, answer="Because")

            db.session.add(question)
            db.session.commit()

    def test_question_must_not_be_empty(self):
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            question = BriefClarificationQuestion(brief=self.brief, question="", answer="Because")
            question.validate()

        assert e.value.message["question"] == "answer_required"

    def test_questions_must_not_be_more_than_100_words(self):
        long_question = " ".join(["word"] * 101)
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            question = BriefClarificationQuestion(brief=self.brief, question=long_question, answer="Because")
            question.validate()

        assert e.value.message["question"] == "under_100_words"

    def test_question_must_not_be_more_than_5000_characters(self):
        long_question = "a" * 5001
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            question = BriefClarificationQuestion(brief=self.brief, question=long_question, answer="Because")
            question.validate()

        assert e.value.message["question"] == "under_character_limit"

    def test_questions_can_be_100_words(self):
        question = " ".join(["word"] * 100)
        with self.app.app_context():
            question = BriefClarificationQuestion(brief=self.brief, question=question, answer="Because")
            question.validate()

    def test_answer_must_not_be_null(self):
        with self.app.app_context(), pytest.raises(IntegrityError):
            question = BriefClarificationQuestion(brief=self.brief, question="Why?")

            db.session.add(question)
            db.session.commit()

    def test_answer_must_not_be_empty(self):
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            question = BriefClarificationQuestion(brief=self.brief, question="Why?", answer="")
            question.validate()

        assert e.value.message["answer"] == "answer_required"

    def test_answers_must_not_be_more_than_100_words(self):
        long_answer = " ".join(["word"] * 101)
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            question = BriefClarificationQuestion(brief=self.brief, question="Why?", answer=long_answer)
            question.validate()

        assert e.value.message["answer"] == "under_100_words"

    def test_answer_must_not_be_more_than_5000_characters(self):
        long_answer = "a" * 5001
        with self.app.app_context(), pytest.raises(ValidationError) as e:
            question = BriefClarificationQuestion(brief=self.brief, question="Why?", answer=long_answer)
            question.validate()

        assert e.value.message["answer"] == "under_character_limit"

    def test_answers_can_be_100_words(self):
        answer = " ".join(["word"] * 100)
        with self.app.app_context():
            question = BriefClarificationQuestion(brief=self.brief, question="Why?", answer=answer)
            question.validate()


class TestSuppliers(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestSuppliers, self).setup()
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            self.supplier = Supplier.query.filter(Supplier.supplier_id == 0).first()
            self.contact_id = ContactInformation.query.filter(
                ContactInformation.supplier_id == self.supplier.supplier_id
            ).first().id

    def _update_supplier_from_json_with_all_details(self):
        update_data = {
            "id": 90006000,
            "supplierId": "DO_NOT_UPDATE_ME",
            "name": "String and Sticky Tape Inc.",
            "clients": ["Parcel Wrappers Ltd"],
            "dunsNumber": "01010101",
            "eSourcingId": "020202",
            "description": "All your parcel wrapping needs catered for",
            "companiesHouseNumber": "98765432",
            "registeredName": "Tape and String Inc.",
            "registrationCountry": "Wales",
            "otherCompanyRegistrationNumber": "",
            "registrationDate": "1973-08-10",
            "vatNumber": "321321321",
            "organisationSize": "medium",
            "tradingStatus": "Sticky",
        }
        self.supplier.update_from_json(update_data)

    def test_serialization_of_new_supplier(self):
        with mock.patch('app.models.main.url_for') as url_for:
            url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
            assert self.supplier.serialize() == {
                'clients': [],
                'contactInformation': [
                    {
                        'contactName': u'Contact for Supplier 0',
                        'email': u'0@contact.com',
                        'id': self.contact_id,
                        'links': {
                            'self': (
                                ('main.update_contact_information',),
                                {'contact_id': self.contact_id, 'supplier_id': 0}
                            )
                        },
                        'postcode': u'SW1A 1AA',
                    }
                ],
                'description': u'',
                'id': 0,
                'links': {
                    'self': (('main.get_supplier',), {'supplier_id': 0})
                },
                'name': u'Supplier 0',
            }

    def test_update_from_json(self):
        with self.app.app_context():
            initial_id = self.supplier.id
            initial_sid = self.supplier.supplier_id

            self._update_supplier_from_json_with_all_details()

            # Check IDs can't be updated
            assert self.supplier.id == initial_id
            assert self.supplier.supplier_id == initial_sid

            # Check everything else has been updated to the correct value
            assert self.supplier.name == "String and Sticky Tape Inc."
            assert self.supplier.clients == ["Parcel Wrappers Ltd"]
            assert self.supplier.duns_number == "01010101"
            assert self.supplier.esourcing_id == "020202"
            assert self.supplier.description == "All your parcel wrapping needs catered for"
            assert self.supplier.companies_house_number == "98765432"
            assert self.supplier.registered_name == "Tape and String Inc."
            assert self.supplier.registration_country == "Wales"
            assert self.supplier.other_company_registration_number == ""
            assert self.supplier.registration_date == datetime(1973, 8, 10, 0, 0)
            assert self.supplier.vat_number == "321321321"
            assert self.supplier.organisation_size == "medium"
            assert self.supplier.trading_status == "Sticky"

            # Check that serialization of a supplier with all details added looks as it should
            with mock.patch('app.models.main.url_for') as url_for:
                url_for.side_effect = lambda *args, **kwargs: (args, kwargs)
                assert self.supplier.serialize() == {
                    'clients': ['Parcel Wrappers Ltd'],
                    'companiesHouseNumber': '98765432',
                    'contactInformation': [
                        {
                            'contactName': u'Contact for Supplier 0',
                            'email': u'0@contact.com',
                            'id': self.contact_id,
                            'links': {
                                'self': (
                                    ('main.update_contact_information',),
                                    {'contact_id': self.contact_id, 'supplier_id': 0}
                                )
                            },
                            'postcode': u'SW1A 1AA',
                        }
                    ],
                    'description': 'All your parcel wrapping needs catered for',
                    'dunsNumber': '01010101',
                    'eSourcingId': '020202',
                    'id': 0,
                    'links': {'self': (('main.get_supplier',), {'supplier_id': 0})},
                    'name': 'String and Sticky Tape Inc.',
                    'organisationSize': 'medium',
                    'otherCompanyRegistrationNumber': '',
                    'registeredName': 'Tape and String Inc.',
                    'registrationCountry': 'Wales',
                    'registrationDate': '1973-08-10',
                    'tradingStatus': 'Sticky',
                    'vatNumber': '321321321',
                }

    def test_update_from_json_error_for_badly_formatted_date(self):
        with self.app.app_context():
            with pytest.raises(ValidationError) as exception_info:
                self.supplier.update_from_json({"registrationDate": "July 4, 1776"})
            assert "Registration date format must be %Y-%m-%d" in "{}".format(exception_info.value)


class TestServices(BaseApplicationTest, FixtureMixin):
    def test_framework_is_live_only_returns_live_frameworks(self):
        with self.app.app_context():
            # the side effect of this method is to create four suppliers with ids between 0-3
            self.setup_dummy_services_including_unpublished(1)
            self.setup_dummy_service(
                service_id='1000000000',
                supplier_id=0,
                status='published',
                framework_id=2)

            services = Service.query.framework_is_live()

            assert_equal(Service.query.count(), 4)
            assert_equal(services.count(), 3)
            assert(all(s.framework.status == 'live' for s in services))

    def test_lot_must_be_associated_to_the_framework(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            with pytest.raises(IntegrityError) as excinfo:
                self.setup_dummy_service(
                    service_id='10000000001',
                    supplier_id=0,
                    framework_id=5,  # Digital Outcomes and Specialists
                    lot_id=1)  # SaaS

            assert 'not present in table "framework_lots"' in "{}".format(excinfo.value)

    def test_default_ordering(self):
        def add_service(service_id, framework_id, lot_id, service_name):
            self.setup_dummy_service(
                service_id=service_id,
                supplier_id=0,
                framework_id=framework_id,
                lot_id=lot_id,
                data={'serviceName': service_name})

        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            add_service('1000000990', 3, 3, 'zzz')
            add_service('1000000991', 3, 3, 'aaa')
            add_service('1000000992', 3, 1, 'zzz')
            add_service('1000000993', 1, 3, 'zzz')
            db.session.commit()

            services = Service.query.default_order()

            assert_equal(
                [s.service_id for s in services],
                ['1000000993', '1000000992', '1000000991', '1000000990'])

    def test_has_statuses(self):
        with self.app.app_context():
            self.setup_dummy_services_including_unpublished(1)

            services = Service.query.has_statuses('published')

            assert_equal(services.count(), 1)

    def test_in_lot(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            self.setup_dummy_service(
                service_id='10000000001',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=5)  # digital-outcomes
            self.setup_dummy_service(
                service_id='10000000002',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6)  # digital-specialists
            self.setup_dummy_service(
                service_id='10000000003',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6)  # digital-specialists

            services = Service.query.in_lot('digital-specialists')
            assert services.count() == 2

    def test_data_has_key(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            self.setup_dummy_service(
                service_id='10000000001',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6,  # digital-specialists
                data={'key1': 'foo', 'key2': 'bar'})
            self.setup_dummy_service(
                service_id='10000000002',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6,  # digital-specialists
                data={'key1': 'blah'})
            services = Service.query.data_has_key('key1')
            assert services.count() == 2

            services = Service.query.data_has_key('key2')
            assert services.count() == 1

            services = Service.query.data_has_key('key3')
            assert services.count() == 0

    def test_data_key_contains_value(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            self.setup_dummy_service(
                service_id='10000000001',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6,  # digital-specialists
                data={'key1': ['foo1', 'foo2'], 'key2': ['bar1']})
            self.setup_dummy_service(
                service_id='10000000002',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6,  # digital-specialists
                data={'key1': ['foo1', 'foo3']})
            services = Service.query.data_key_contains_value('key1', 'foo1')
            assert services.count() == 2

            services = Service.query.data_key_contains_value('key2', 'bar1')
            assert services.count() == 1

            services = Service.query.data_key_contains_value('key3', 'foo1')
            assert services.count() == 0

            services = Service.query.data_key_contains_value('key1', 'bar1')
            assert services.count() == 0

    def test_service_status(self):
        service = Service(status='enabled')

        assert_equal(service.status, 'enabled')

    def test_invalid_service_status(self):
        service = Service()
        with assert_raises(ValidationError):
            service.status = 'invalid'

    def test_has_statuses_should_accept_multiple_statuses(self):
        with self.app.app_context():
            self.setup_dummy_services_including_unpublished(1)

            services = Service.query.has_statuses('published', 'disabled')

            assert_equal(services.count(), 2)

    def test_update_from_json(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            self.setup_dummy_service(
                service_id='1000000000',
                supplier_id=0,
                status='published',
                framework_id=2)

            service = Service.query.filter(Service.service_id == '1000000000').first()

            updated_at = service.updated_at
            created_at = service.created_at

            service.update_from_json({'foo': 'bar'})

            db.session.add(service)
            db.session.commit()

            assert service.created_at == created_at
            assert service.updated_at > updated_at
            assert service.data == {'foo': 'bar', 'serviceName': 'Service 1000000000'}


class TestSupplierFrameworks(BaseApplicationTest, FixtureMixin):
    def test_nulls_are_stripped_from_declaration(self):
        supplier_framework = SupplierFramework()
        supplier_framework.declaration = {'foo': 'bar', 'bar': None}

        assert supplier_framework.declaration == {'foo': 'bar'}

    def test_whitespace_values_are_stripped_from_declaration(self):
        supplier_framework = SupplierFramework()
        supplier_framework.declaration = {'foo': ' bar ', 'bar': '', 'other': ' '}

        assert supplier_framework.declaration == {'foo': 'bar', 'bar': '', 'other': ''}

    def test_create_supplier_framework(self):
        # the intention of this test is to ensure a SupplierFramework without any FrameworkAgreements is visible through
        # the default query - i.e. none of our custom relationships are causing it to do an inner join which would
        # cause such a SupplierFramework to be invisible
        with self.app.app_context():
            self.setup_dummy_suppliers(1)

            supplier_framework = SupplierFramework(supplier_id=0, framework_id=1)
            db.session.add(supplier_framework)
            db.session.commit()

            assert len(
                SupplierFramework.query.filter(
                    SupplierFramework.supplier_id == 0
                ).all()
            ) == 1

    def test_prefill_declaration_from_framework(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(2)

            supplier_framework0 = SupplierFramework(supplier_id=0, framework_id=1)
            db.session.add(supplier_framework0)

            supplier_framework1 = SupplierFramework(
                supplier_id=0,
                framework_id=2,
                prefill_declaration_from_framework_id=1,
            )
            db.session.add(supplier_framework1)

            db.session.commit()

            # check the relationships operate properly
            assert supplier_framework1.prefill_declaration_from_framework is supplier_framework0.framework
            assert supplier_framework1.prefill_declaration_from_supplier_framework is supplier_framework0

            # check the serialization does the right thing
            assert supplier_framework0.serialize()["prefillDeclarationFromFrameworkSlug"] is None
            assert supplier_framework1.serialize()["prefillDeclarationFromFrameworkSlug"] == \
                supplier_framework0.framework.slug

            # before we tear things down we'll test prefill_declaration_from_framework's
            # SupplierFramework->SupplierFramework constraint
            db.session.delete(supplier_framework0)
            with pytest.raises(IntegrityError):
                # this should fail because it removes the sf that supplier_framework1 implicitly points to
                db.session.commit()


class TestLot(BaseApplicationTest):
    def test_lot_data_is_serialized(self):
        with self.app.app_context():
            self.framework = Framework.query.filter(Framework.slug == 'digital-outcomes-and-specialists').first()
            self.lot = self.framework.get_lot('user-research-studios')

            assert self.lot.serialize() == {
                u'id': 7,
                u'name': u'User research studios',
                u'slug': u'user-research-studios',
                u'allowsBrief': False,
                u'oneServiceLimit': False,
                u'unitSingular': u'lab',
                u'unitPlural': u'labs',
            }


class TestFrameworkSupplierIds(BaseApplicationTest):
    """Test getting supplier ids for framework."""

    def test_1_supplier(self, draft_service):
        """Test that when one supplier exists in the framework that only supplier is shown."""
        with self.app.app_context():
            ds = DraftService.query.filter(DraftService.service_id == draft_service['serviceId']).first()
            f = Framework.query.filter(Framework.id == ds.framework_id).first()
            supplier_ids_with_completed_service = f.get_supplier_ids_for_completed_service()
            assert len(supplier_ids_with_completed_service) == 1
            assert ds.supplier.supplier_id in supplier_ids_with_completed_service

    def test_submitted_shows(self, draft_service):
        """Test sevice with status 'submitted' is shown."""
        with self.app.app_context():
            ds = DraftService.query.filter(DraftService.service_id == draft_service['serviceId']).first()
            f = Framework.query.filter(Framework.id == ds.framework_id).first()
            supplier_ids_with_completed_service = f.get_supplier_ids_for_completed_service()
            assert ds.status == 'submitted'
            assert ds.supplier.supplier_id in supplier_ids_with_completed_service

    def test_failed_shows(self, draft_service):
        """Test sevice with status 'failed' is shown."""
        with self.app.app_context():
            ds = DraftService.query.filter(DraftService.service_id == draft_service['serviceId']).first()
            ds.status = 'failed'
            db.session.add(ds)
            db.session.commit()
            f = Framework.query.filter(Framework.id == ds.framework_id).first()
            supplier_ids_with_completed_service = f.get_supplier_ids_for_completed_service()
            assert ds.status == 'failed'
            assert ds.supplier.supplier_id in supplier_ids_with_completed_service

    def test_not_submitted_does_not_show(self, draft_service):
        """Test sevice with status 'not-submitted' is not shown."""
        with self.app.app_context():
            ds = DraftService.query.filter(DraftService.service_id == draft_service['serviceId']).first()
            ds.status = 'not-submitted'
            db.session.add(ds)
            db.session.commit()
            f = Framework.query.filter(Framework.id == ds.framework_id).first()
            supplier_ids_with_completed_service = f.get_supplier_ids_for_completed_service()
            assert ds.status == 'not-submitted'
            assert ds.supplier.supplier_id not in supplier_ids_with_completed_service

    def test_no_suppliers(self, open_example_framework):
        """Test a framework with no suppliers on it returns no submitted services."""
        with self.app.app_context():
            f = Framework.query.filter(Framework.id == open_example_framework['id']).first()
            supplier_ids_with_completed_service = f.get_supplier_ids_for_completed_service()
            assert len(supplier_ids_with_completed_service) == 0


class TestFrameworkSupplierIdsMany(BaseApplicationTest, FixtureMixin):
    """Test multiple suppliers, multiple services."""

    def test_multiple_services(self):
        with self.app.app_context():
            self.setup_dos_2_framework()
            lot = Lot.query.first()
            self.fl_query = {
                'framework_id': 101,
                'lot_id': lot.id
            }
            fl = FrameworkLot(**self.fl_query)
            db.session.add(fl)
            db.session.commit()

            # Set u 5 dummy suppliers
            self.setup_dummy_suppliers(5)
            supplier_ids = range(5)
            # 5 sets of statuses for their respective services.
            service_status_choices = [
                ('failed',),
                ('not-submitted',),
                ('failed', 'failed', 'failed', 'not-submitted', 'submitted', 'submitted', 'not-submitted', 'failed'),
                (),
                ('not-submitted', 'submitted', 'not-submitted', 'not-submitted', 'failed')
            ]
            # For the supplier, service_status sets create the services and draft services.
            count = 0
            for supplier_id, service_statuses in zip(supplier_ids, service_status_choices):
                for service_status in service_statuses:
                    service_id = str(count) * 10
                    count += 1
                    self.setup_dummy_service(service_id, supplier_id=supplier_id, **self.fl_query)

                    db.session.commit()
                    with mock.patch('app.models.main.url_for', autospec=lambda i, **values: 'test.url/test'):
                        ds = DraftService.from_service(Service.query.filter(Service.service_id == service_id).first())
                        ds.status = service_status
                    db.session.add(ds)
                    db.session.commit()
            # Assert that only those suppliers whose service_status list contains failed and/ or submitted are returned.
            framework = Framework.query.filter(Framework.id == 101).first()
            assert sorted(framework.get_supplier_ids_for_completed_service()) == [0, 2, 4]


class TestFrameworkAgreements(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestFrameworkAgreements, self).setup()
        with self.app.app_context():
            self.setup_dummy_suppliers(1)

            supplier_framework = SupplierFramework(supplier_id=0, framework_id=1)
            db.session.add(supplier_framework)
            db.session.commit()

    def test_supplier_has_to_be_associated_with_a_framework(self):
        with self.app.app_context():
            # Supplier 0 and SupplierFramework(supplier_id=0, framework_id=1) are created in setup() so these IDs exist
            framework_agreement = FrameworkAgreement(supplier_id=0, framework_id=1)
            db.session.add(framework_agreement)
            db.session.commit()

            assert framework_agreement.id

    def test_supplier_cannot_have_a_framework_agreement_for_a_framework_they_are_not_associated_with(self):
        with self.app.app_context():
            # SupplierFramework(supplier_id=0, framework_id=2) does not exist so this should fail
            framework_agreement = FrameworkAgreement(supplier_id=0, framework_id=2)
            db.session.add(framework_agreement)

            with pytest.raises(IntegrityError):
                db.session.commit()

    def test_new_framework_agreement_status_is_draft(self):
        with self.app.app_context():
            framework_agreement = FrameworkAgreement(supplier_id=0, framework_id=1)
            db.session.add(framework_agreement)
            db.session.commit()

            # Check python implementation gives same result as the sql implementation
            assert framework_agreement.status == 'draft'
            assert FrameworkAgreement.query.all()[0].status == 'draft'

    def test_partially_signed_framework_agreement_status_is_draft(self):
        with self.app.app_context():
            framework_agreement = FrameworkAgreement(
                supplier_id=0,
                framework_id=1,
                signed_agreement_details={'agreement': 'details'},
                signed_agreement_path='path'
            )
            db.session.add(framework_agreement)
            db.session.commit()

            # Check python implementation gives same result as the sql implementation
            assert framework_agreement.status == 'draft'
            assert FrameworkAgreement.query.all()[0].status == 'draft'

    def test_signed_framework_agreement_status_is_signed(self):
        with self.app.app_context():
            framework_agreement = FrameworkAgreement(
                supplier_id=0,
                framework_id=1,
                signed_agreement_details={'agreement': 'details'},
                signed_agreement_path='path',
                signed_agreement_returned_at=datetime.utcnow()
            )
            db.session.add(framework_agreement)
            db.session.commit()

            # Check python implementation gives same result as the sql implementation
            assert framework_agreement.status == 'signed'
            assert FrameworkAgreement.query.all()[0].status == 'signed'

    def test_on_hold_framework_agreement_status_is_on_hold(self):
        with self.app.app_context():
            framework_agreement = FrameworkAgreement(
                supplier_id=0,
                framework_id=1,
                signed_agreement_details={'agreement': 'details'},
                signed_agreement_path='path',
                signed_agreement_returned_at=datetime.utcnow(),
                signed_agreement_put_on_hold_at=datetime.utcnow()
            )
            db.session.add(framework_agreement)
            db.session.commit()

            # Check python implementation gives same result as the sql implementation
            assert framework_agreement.status == 'on-hold'
            assert FrameworkAgreement.query.all()[0].status == 'on-hold'

    def test_approved_framework_agreement_status_is_approved(self):
        with self.app.app_context():
            framework_agreement = FrameworkAgreement(
                supplier_id=0,
                framework_id=1,
                signed_agreement_details={'agreement': 'details'},
                signed_agreement_path='path',
                signed_agreement_returned_at=datetime.utcnow(),
                countersigned_agreement_returned_at=datetime.utcnow()
            )
            db.session.add(framework_agreement)
            db.session.commit()

            # Check python implementation gives same result as the sql implementation
            assert framework_agreement.status == 'approved'
            assert FrameworkAgreement.query.all()[0].status == 'approved'

    def test_countersigned_framework_agreement_status_is_countersigned(self):
        with self.app.app_context():
            framework_agreement = FrameworkAgreement(
                supplier_id=0,
                framework_id=1,
                signed_agreement_details={'agreement': 'details'},
                signed_agreement_path='path',
                signed_agreement_returned_at=datetime.utcnow(),
                countersigned_agreement_returned_at=datetime.utcnow(),
                countersigned_agreement_path='/path/to/the/countersignedAgreement.pdf'
            )
            db.session.add(framework_agreement)
            db.session.commit()

            # Check python implementation gives same result as the sql implementation
            assert framework_agreement.status == 'countersigned'
            assert FrameworkAgreement.query.all()[0].status == 'countersigned'

    def test_most_recent_signature_time(self):
        framework_agreement = FrameworkAgreement(
            supplier_id=0,
            framework_id=1,
        )
        assert framework_agreement.most_recent_signature_time is None

        framework_agreement.signed_agreement_details = {'agreement': 'details'}
        framework_agreement.signed_agreement_path = '/path/to/the/agreement.pdf'
        framework_agreement.signed_agreement_returned_at = datetime(2016, 9, 10, 11, 12, 0, 0)

        assert framework_agreement.most_recent_signature_time == datetime(2016, 9, 10, 11, 12, 0, 0)

        framework_agreement.countersigned_agreement_path = '/path/to/the/countersignedAgreement.pdf'
        framework_agreement.countersigned_agreement_returned_at = datetime(2016, 10, 11, 10, 12, 0, 0)

        assert framework_agreement.most_recent_signature_time == datetime(2016, 10, 11, 10, 12, 0, 0)


class TestCurrentFrameworkAgreement(BaseApplicationTest, FixtureMixin):
    """
    Tests the current_framework_agreement property of SupplierFramework objects
    """
    BASE_AGREEMENT_KWARGS = {
        "supplier_id": 0,
        "framework_id": 1,
        "signed_agreement_details": {"agreement": "details"},
        "signed_agreement_path": "path",
    }

    def setup(self):
        super(TestCurrentFrameworkAgreement, self).setup()
        with self.app.app_context():
            self.setup_dummy_suppliers(1)

            supplier_framework = SupplierFramework(supplier_id=0, framework_id=1)
            db.session.add(supplier_framework)
            db.session.commit()

    def get_supplier_framework(self):
        return SupplierFramework.query.filter(
            SupplierFramework.supplier_id == 0,
            SupplierFramework.framework_id == 1
        ).first()

    def test_current_framework_agreement_with_no_agreements(self):
        with self.app.app_context():
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement is None

    def test_current_framework_agreement_with_one_draft_only(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(id=5, **self.BASE_AGREEMENT_KWARGS))
            db.session.commit()
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement is None

    def test_current_framework_agreement_with_multiple_drafts(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(id=5, **self.BASE_AGREEMENT_KWARGS))
            db.session.add(FrameworkAgreement(id=6, **self.BASE_AGREEMENT_KWARGS))
            db.session.commit()
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement is None

    def test_current_framework_agreement_with_one_signed(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(
                id=5, signed_agreement_returned_at=datetime(2016, 10, 9, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement.id == 5

    def test_current_framework_agreement_with_multiple_signed(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(
                id=5, signed_agreement_returned_at=datetime(2016, 10, 9, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            db.session.add(FrameworkAgreement(
                id=6, signed_agreement_returned_at=datetime(2016, 10, 10, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement.id == 6

    def test_current_framework_agreement_with_signed_and_old_draft_does_not_return_draft(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(id=5, **self.BASE_AGREEMENT_KWARGS))
            db.session.add(FrameworkAgreement(
                id=6, signed_agreement_returned_at=datetime(2016, 10, 10, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement.id == 6

    def test_current_framework_agreement_with_signed_and_new_draft_does_not_return_draft(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(id=6, **self.BASE_AGREEMENT_KWARGS))
            db.session.add(FrameworkAgreement(
                id=5, signed_agreement_returned_at=datetime(2016, 10, 10, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement.id == 5

    def test_current_framework_agreement_with_signed_and_new_countersigned(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(
                id=5, signed_agreement_returned_at=datetime(2016, 10, 9, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            db.session.add(FrameworkAgreement(
                id=6,
                signed_agreement_returned_at=datetime(2016, 10, 10, 12, 00, 00),
                countersigned_agreement_returned_at=datetime(2016, 10, 11, 12, 00, 00),
                **self.BASE_AGREEMENT_KWARGS)
            )
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement.id == 6

    def test_current_framework_agreement_with_countersigned_and_new_signed(self):
        with self.app.app_context():
            db.session.add(FrameworkAgreement(
                id=5, signed_agreement_returned_at=datetime(2016, 10, 11, 12, 00, 00), **self.BASE_AGREEMENT_KWARGS)
            )
            db.session.add(FrameworkAgreement(
                id=6,
                signed_agreement_returned_at=datetime(2016, 10, 9, 12, 00, 00),
                countersigned_agreement_returned_at=datetime(2016, 10, 10, 12, 00, 00),
                **self.BASE_AGREEMENT_KWARGS)
            )
            supplier_framework = self.get_supplier_framework()
            assert supplier_framework.current_framework_agreement.id == 5