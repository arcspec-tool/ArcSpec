import io
import secrets
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from weasyprint import HTML

from apps.accounts.models import User
from apps.administration.models import SystemSettings
from apps.doctemplates.models import Template, TemplateAttribute, TemplateSection
from apps.notifications.models import AuditLog, Notification
from apps.projects.models import (
    Attachment,
    Comment,
    Item,
    ItemAttributeValue,
    ItemTag,
    Project,
    ProjectMembership,
    ProjectVersion,
    SavedView,
    Tag,
    TraceabilityLink,
)

USERS = [
    {'key': 'maria', 'email': 'maria.lopez@example.com', 'first_name': 'Maria', 'last_name': 'Lopez', 'system_role': 'admin', 'department': 'IT Operations', 'avatar_color': '#284E8A', 'joined': 80},
    {'key': 'tom', 'email': 'tom.becker@example.com', 'first_name': 'Tom', 'last_name': 'Becker', 'system_role': 'user', 'department': 'Product Management', 'avatar_color': '#7c3aed', 'joined': 78},
    {'key': 'aisha', 'email': 'aisha.khan@example.com', 'first_name': 'Aisha', 'last_name': 'Khan', 'system_role': 'user', 'department': 'Business Analysis', 'avatar_color': '#ea580c', 'joined': 76},
    {'key': 'jonas', 'email': 'jonas.petersen@example.com', 'first_name': 'Jonas', 'last_name': 'Petersen', 'system_role': 'user', 'department': 'Quality Assurance', 'avatar_color': '#16a34a', 'joined': 75},
    {'key': 'elena', 'email': 'elena.rossi@example.com', 'first_name': 'Elena', 'last_name': 'Rossi', 'system_role': 'viewer', 'department': 'Clinic Operations', 'avatar_color': '#0891b2', 'joined': 60},
    {'key': 'daniel', 'email': 'daniel.kim@example.com', 'first_name': 'Daniel', 'last_name': 'Kim', 'system_role': 'user', 'department': 'Software Development', 'avatar_color': '#dc2626', 'joined': 50, 'deactivated': 7},
    {'key': 'sofia', 'email': 'sofia.novak@example.com', 'first_name': 'Sofia', 'last_name': 'Novak', 'system_role': 'user', 'department': 'Software Development', 'avatar_color': '#64748b', 'joined': 2, 'invited': True},
]

PROJECT_TAGS = {
    'booking': [('Notifications', '#0e7490'), ('Scheduling', '#4d7c0f')],
}

CUSTOM_TEMPLATES = [
    {
        'name': 'Change Request',
        'description': 'A request to change approved requirements: the change, its reason, its impact and the decision.',
        'doc_type': 'custom',
        'is_global': True,
        'created_by': 'tom',
        'day': 16,
        'sections': [
            ('1', 'Summary', 'The change in one or two sentences.'),
            ('2', 'Reason', 'Why the change is needed and who asked for it.'),
            ('3', 'Impact', 'What the change affects.'),
            ('3.1', 'Schedule', 'How the change moves dates and milestones.'),
            ('3.2', 'Cost', 'The extra cost of the change.'),
            ('4', 'Decision', 'The decision, who made it and when.'),
        ],
        'attributes': [('Requested By', 'user', []), ('Decision Date', 'date', [])],
    },
    {
        'name': 'Release Notes',
        'description': 'Notes for one release: new features, fixed problems and known issues.',
        'doc_type': 'custom',
        'is_global': False,
        'created_by': 'aisha',
        'day': 8,
        'sections': [
            ('1', 'New Features', 'Features added in this release.'),
            ('2', 'Fixed Problems', 'Problems fixed in this release.'),
            ('3', 'Known Issues', 'Problems that remain in this release and how to work around them.'),
        ],
        'attributes': [('Release', 'text', [])],
    },
]


def p(text):
    return f'<p>{text}</p>'


PROJECTS = [
    {
        'key': 'phone',
        'name': 'Telephone Booking Process',
        'description': 'Requirements for the telephone booking process that the online booking system replaces.',
        'template': 'Software Requirements Specification',
        'color': '#64748b',
        'created_by': 'tom',
        'day': 70,
        'members': [('aisha', 'editor', 70)],
        'items': [
            {'key': 'ph_hours', 'section': '3.2', 'day': 69, 'by': 'tom', 'status': 'approved', 'priority': 'medium',
             'text': p('Reception staff shall answer booking calls between 08:00 and 18:00 on working days.')},
            {'key': 'ph_diary', 'section': '3.2', 'day': 68, 'by': 'aisha', 'status': 'approved', 'priority': 'medium',
             'text': p("Reception staff shall record each telephone booking in the clinic's appointment diary.")},
        ],
        'archived': 20,
    },
    {
        'key': 'booking',
        'name': 'Online Booking System',
        'description': 'Software requirements for the online booking system of Riverside Physio, a network of four physiotherapy clinics.',
        'template': 'Software Requirements Specification',
        'color': '#284E8A',
        'created_by': 'tom',
        'day': 41,
        'members': [('aisha', 'editor', 41), ('jonas', 'editor', 40), ('elena', 'viewer', 38)],
        'items': [
            {'key': 'purpose', 'section': '1.1', 'day': 40, 'by': 'aisha', 'status': 'draft', 'priority': 'medium',
             'text': p("This document specifies the online booking system of Riverside Physio, a network of four physiotherapy clinics. Patients use the system to book, move and cancel appointments. Reception staff use it to manage practitioners' schedules."),
             'changes': [(33, 'tom', 'in-review'), (30, 'tom', 'approved')],
             'attachment': ('workshop', 39, 'aisha')},
            {'key': 'scope', 'section': '1.2', 'day': 40, 'by': 'aisha', 'status': 'draft', 'priority': 'medium',
             'text': p('The system covers online booking, schedule management for reception staff and appointment reminders. Billing, medical records and payroll are out of scope.'),
             'changes': [(30, 'tom', 'approved')]},
            {'key': 'terms', 'section': '1.3', 'day': 39, 'by': 'aisha', 'status': 'approved', 'priority': 'low',
             'text': p('Terms used in this document:') + "<ul><li><strong>Appointment</strong>: a booked time slot with one practitioner at one clinic.</li><li><strong>Slot</strong>: a period in a practitioner's schedule that can hold one appointment.</li><li><strong>Practitioner</strong>: a physiotherapist who treats patients.</li></ul>"},
            {'key': 'perspective', 'section': '2.1', 'day': 37, 'by': 'tom', 'status': 'in-review', 'priority': 'medium',
             'text': p("The booking system replaces booking by telephone. It reads practitioners' working hours from the staff rota system and writes nothing back to it.")},
            {'key': 'functions', 'section': '2.2', 'day': 37, 'by': 'aisha', 'status': 'approved', 'priority': 'high',
             'text': p('Main functions:') + "<ul><li>Patients search free slots and book, move or cancel appointments.</li><li>Reception staff manage practitioners' schedules and book on behalf of patients.</li><li>The system sends confirmations and reminders.</li></ul>"},
            {'key': 'users', 'section': '2.3', 'day': 36, 'by': 'aisha', 'status': 'approved', 'priority': 'low',
             'text': p("Patients book a few times a year and need no training. Reception staff use the system all day and know the clinics' services and practitioners.")},
            {'key': 'gdpr', 'section': '2.4', 'day': 36, 'by': 'tom', 'status': 'approved', 'priority': 'high', 'assignee': 'tom',
             'text': p("The system processes patients' names, phone numbers and email addresses and shall comply with the GDPR."),
             'tags': ['Compliance'], 'attrs': {'Verification Method': 'Inspection', 'Source': 'Data protection officer', 'Stability': 'Stable'}},
            {'key': 'rota', 'section': '2.5', 'day': 35, 'by': 'tom', 'status': 'draft', 'priority': 'medium',
             'text': p('The staff rota system exports working hours at least once a day.'), 'tags': ['API']},
            {'key': 'browsers', 'section': '3.1', 'day': 34, 'by': 'jonas', 'status': 'in-review', 'priority': 'medium', 'assignee': 'jonas',
             'text': p('The booking pages shall work in the current versions of Chrome, Edge, Firefox and Safari.'), 'tags': ['UX'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'Low'}},
            {'key': 'sms_api', 'section': '3.1', 'day': 33, 'by': 'aisha', 'status': 'approved', 'priority': 'medium',
             'text': p("The system shall send SMS messages through the clinics' existing SMS provider."), 'tags': ['API', 'Notifications'],
             'attrs': {'Verification Method': 'Demonstration', 'Risk Level': 'Medium', 'Source': 'Clinic management'}},
            {'key': 'flow', 'section': '3.2', 'day': 33, 'by': 'aisha', 'status': 'approved', 'priority': 'high',
             'text': p('Online booking shall take the patient through four steps: choose a service, choose a free slot, enter contact details and confirm.'),
             'image': ('flow', 'Booking steps'), 'tags': ['UX', 'MVP'],
             'attrs': {'Verification Method': 'Demonstration', 'Risk Level': 'Low', 'Source': 'Reception staff interviews', 'Stability': 'Stable'}},
            {'key': 'search', 'section': '3.2', 'day': 32, 'by': 'aisha', 'status': 'approved', 'priority': 'high', 'assignee': 'aisha',
             'text': p('A patient shall be able to search free slots by clinic, service, practitioner and date.'), 'tags': ['MVP'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'Medium', 'Source': 'Reception staff interviews', 'Stability': 'Stable'}},
            {'key': 'book', 'section': '3.2', 'day': 32, 'by': 'aisha', 'status': 'approved', 'priority': 'high', 'assignee': 'aisha',
             'text': p('A patient shall be able to book a free slot after entering a name, a phone number and an email address.'), 'tags': ['MVP'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'High', 'Source': 'Reception staff interviews', 'Stability': 'Stable'}},
            {'key': 'confirm', 'section': '3.2', 'day': 31, 'by': 'aisha', 'status': 'approved', 'priority': 'medium',
             'text': p('The system shall send a confirmation email within one minute of a booking.'), 'tags': ['Notifications'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'Low', 'Stability': 'Stable'}},
            {'key': 'cancel', 'section': '3.2', 'day': 30, 'by': 'aisha', 'status': 'draft', 'priority': 'high', 'assignee': 'aisha',
             'text': p('A patient shall be able to cancel an appointment up to 24 hours before it starts.'), 'tags': ['MVP'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'Medium', 'Stability': 'Unstable'},
             'changes': [(6, 'aisha', 'in-review')],
             'comments': [
                 ('aisha', 8, 'Does the 24-hour limit apply to reception staff as well?', [
                     ('tom', 7, 'No. Reception staff can cancel at any time. The limit applies to patients only.'),
                 ]),
             ]},
            {'key': 'reschedule', 'section': '3.2', 'day': 30, 'by': 'aisha', 'status': 'in-review', 'priority': 'medium', 'assignee': 'tom',
             'text': p('A patient shall be able to move an appointment to another free slot with the same practitioner.'), 'tags': ['Needs Discussion'],
             'comments': [
                 ('jonas', 2, 'Should moving an appointment also follow the 24-hour limit for cancellations?', []),
             ]},
            {'key': 'reminder', 'section': '3.2', 'day': 29, 'by': 'tom', 'status': 'in-review', 'priority': 'medium', 'assignee': 'jonas',
             'text': p('The system shall send an SMS reminder 24 hours before each appointment.'), 'tags': ['Notifications'],
             'changes': [(20, 'tom', 'approved')], 'attachment': ('sms_texts', 28, 'tom'),
             'comments': [
                 ('jonas', 25, 'The SMS provider charges for each message. Do we send a reminder for appointments booked less than 24 hours ahead?', [
                     ('tom', 24, 'No. The confirmation email is enough for those.'),
                 ]),
             ]},
            {'key': 'staff_book', 'section': '3.2', 'day': 28, 'by': 'tom', 'status': 'approved', 'priority': 'high',
             'text': p('Reception staff shall be able to book, move and cancel appointments on behalf of a patient.'), 'tags': ['MVP']},
            {'key': 'block', 'section': '3.2', 'day': 27, 'by': 'tom', 'status': 'draft', 'priority': 'medium', 'assignee': 'tom',
             'text': p("Reception staff shall be able to block time in a practitioner's schedule for holidays, training and meetings."), 'tags': ['Scheduling'],
             'changes': [(1, 'tom', 'in-review')], 'attachment': ('opening_hours', 27, 'tom'),
             'comments': [
                 ('aisha', 1, 'Should patients see blocked time as unavailable, or should those slots not appear at all?', []),
             ]},
            {'key': 'daylist', 'section': '3.2', 'day': 26, 'by': 'aisha', 'status': 'draft', 'priority': 'low',
             'text': p("The system shall show each practitioner a list of the day's appointments, sorted by start time."), 'tags': ['Scheduling']},
            {'key': 'double', 'section': '3.2', 'day': 25, 'by': 'jonas', 'status': 'approved', 'priority': 'high', 'assignee': 'jonas',
             'text': p('The system shall not allow two appointments in the same slot for one practitioner, also when two patients book at the same moment.'), 'tags': ['Database'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'High', 'Stability': 'Stable'}},
            {'key': 'deposit', 'section': '3.2', 'day': 24, 'by': 'tom', 'status': 'draft', 'priority': 'low',
             'text': p('The system shall take a deposit payment by card when a patient books.'),
             'changes': [(22, 'tom', 'in-review'), (18, 'tom', 'rejected')],
             'comments': [
                 ('tom', 18, "Rejected at the review meeting. Payments stay in the clinics' billing system.", []),
             ]},
            {'key': 'perf_search', 'section': '3.3', 'day': 23, 'by': 'jonas', 'status': 'in-review', 'priority': 'medium', 'assignee': 'jonas',
             'text': p('Search results shall appear within 2 seconds for 95% of searches.'), 'tags': ['Performance'],
             'attrs': {'Verification Method': 'Test', 'Risk Level': 'Medium', 'Stability': 'Stable'},
             'changes': [(2, 'jonas', 'approved')],
             'comments': [
                 ('jonas', 4, 'Measured on the staging system with 500 simulated users: 95% of searches returned within 1.4 seconds.', []),
             ]},
            {'key': 'perf_users', 'section': '3.3', 'day': 23, 'by': 'jonas', 'status': 'draft', 'priority': 'medium',
             'text': p('The system shall serve 500 users at the same time within the response times of this section.'), 'tags': ['Performance']},
            {'key': 'eu', 'section': '3.4', 'day': 21, 'by': 'tom', 'status': 'approved', 'priority': 'high', 'assignee': 'tom',
             'text': p('The system shall store all personal data in data centres in the European Union.'), 'tags': ['Compliance', 'Security'],
             'attrs': {'Verification Method': 'Inspection', 'Risk Level': 'High', 'Source': 'Data protection officer', 'Stability': 'Stable'}},
            {'key': 'availability', 'section': '3.5', 'day': 20, 'by': 'tom', 'status': 'in-review', 'priority': 'medium',
             'text': p('The system shall be available 99.5% of each month, not counting maintenance announced 48 hours in advance.')},
            {'key': 'wcag', 'section': '3.5', 'day': 19, 'by': 'aisha', 'status': 'draft', 'priority': 'medium',
             'text': p('The booking pages shall meet WCAG 2.1 level AA.'), 'tags': ['UX', 'Compliance'],
             'comments': [
                 ('elena', 3, "Reception staff asked for larger text on the practitioners' daily lists as well.", []),
             ]},
        ],
    },
    {
        'key': 'gdpr',
        'name': 'Patient Data Protection Record',
        'description': 'GDPR records for the personal data that the online booking system processes.',
        'template': 'GDPR Compliance Documentation',
        'color': '#be185d',
        'created_by': 'aisha',
        'day': 34,
        'members': [('tom', 'editor', 34), ('elena', 'viewer', 33)],
        'items': [
            {'key': 'g_controller', 'section': '1.1', 'day': 34, 'by': 'aisha', 'status': 'approved', 'priority': 'medium',
             'text': p('Controller: Riverside Physio. Contact: the clinic manager of each clinic.'),
             'attrs': {'Compliance Status': 'Compliant', 'Evidence': 'Company register entry'}},
            {'key': 'g_ropa', 'section': '1.3', 'day': 33, 'by': 'aisha', 'status': 'approved', 'priority': 'high',
             'text': p('Processing activity: online appointment booking. Data: name, phone number, email address, service and appointment time.'),
             'attrs': {'Compliance Status': 'Compliant', 'Evidence': 'Record of processing, booking system entry'}},
            {'key': 'g_retention', 'section': '1.5', 'day': 32, 'by': 'aisha', 'status': 'in-review', 'priority': 'high', 'assignee': 'tom',
             'text': p('Appointment data is kept for 24 months after the appointment and then deleted.'),
             'attrs': {'Compliance Status': 'Not compliant', 'Evidence': 'The deletion job is not built yet'}},
            {'key': 'g_basis', 'section': '2.2', 'day': 31, 'by': 'tom', 'status': 'in-review', 'priority': 'medium',
             'text': p('Lawful basis for booking: performance of a contract with the patient. Lawful basis for reminders: legitimate interest.'),
             'attrs': {'Compliance Status': 'Partially compliant', 'Evidence': 'Legitimate interest assessment in progress'}},
            {'key': 'g_access', 'section': '3.3', 'day': 29, 'by': 'aisha', 'status': 'approved', 'priority': 'medium',
             'text': p('Patients ask reception for a copy of their booking data. Reception answers within one month.'),
             'attrs': {'Compliance Status': 'Compliant', 'Evidence': 'Reception procedure, version 2'}},
            {'key': 'g_processor', 'section': '5.2', 'day': 27, 'by': 'tom', 'status': 'approved', 'priority': 'medium',
             'text': p('A data processing agreement is signed with the SMS provider.'),
             'attrs': {'Compliance Status': 'Compliant', 'Evidence': 'Signed agreement in the contracts folder'}},
        ],
    },
    {
        'key': 'testplan',
        'name': 'Online Booking System Test Plan',
        'description': 'Test plan and test cases for release 1.0 of the online booking system.',
        'template': 'Software Test Documentation',
        'color': '#16a34a',
        'created_by': 'jonas',
        'day': 22,
        'members': [('tom', 'editor', 22), ('aisha', 'viewer', 22)],
        'items': [
            {'key': 'tp_id', 'section': '1.1', 'day': 22, 'by': 'jonas', 'status': 'approved', 'priority': 'low',
             'text': p('Test plan TP-BOOK-01 for release 1.0 of the online booking system.')},
            {'key': 'tp_items', 'section': '1.3', 'day': 22, 'by': 'jonas', 'status': 'approved', 'priority': 'medium',
             'text': p('Booking web application release 1.0 and the SMS reminder service.')},
            {'key': 'tp_features', 'section': '1.4', 'day': 21, 'by': 'jonas', 'status': 'approved', 'priority': 'medium',
             'text': p('Search, booking, cancellation, moving appointments, confirmations and reminders.')},
            {'key': 'tp_not', 'section': '1.5', 'day': 21, 'by': 'jonas', 'status': 'in-review', 'priority': 'low',
             'text': p('Card payments. The requirement for a booking deposit was rejected.')},
            {'key': 'tp_approach', 'section': '1.6', 'day': 20, 'by': 'jonas', 'status': 'in-review', 'priority': 'medium',
             'text': p('Functional tests are run by hand on the staging system. Response times are measured with a load test of 500 simulated users.')},
            {'key': 'tp_env', 'section': '1.10', 'day': 20, 'by': 'jonas', 'status': 'draft', 'priority': 'medium',
             'text': p('A staging system with a copy of the clinic list and test practitioners, and a test account at the SMS provider.')},
            {'key': 'tc_book', 'section': '3.2', 'day': 19, 'by': 'jonas', 'status': 'approved', 'priority': 'high', 'assignee': 'jonas',
             'text': p('Book a free slot as a patient. The confirmation email arrives within one minute.'),
             'attrs': {'Test Type': 'System', 'Automated': 'false', 'Test Environment': 'Staging'}},
            {'key': 'tc_cancel_ok', 'section': '3.2', 'day': 18, 'by': 'jonas', 'status': 'approved', 'priority': 'high',
             'text': p('Cancel an appointment that starts in 25 hours. The cancellation succeeds and the slot becomes free.'),
             'attrs': {'Test Type': 'System', 'Automated': 'true', 'Test Environment': 'Staging, CI/CD'}},
            {'key': 'tc_cancel_late', 'section': '3.2', 'day': 18, 'by': 'jonas', 'status': 'in-review', 'priority': 'high',
             'text': p("Try to cancel an appointment that starts in 23 hours. The system refuses and shows the clinic's phone number."),
             'attrs': {'Test Type': 'System', 'Automated': 'true', 'Test Environment': 'Staging, CI/CD'}},
            {'key': 'tc_double', 'section': '3.2', 'day': 17, 'by': 'jonas', 'status': 'in-review', 'priority': 'high', 'assignee': 'tom',
             'text': p('Two patients book the same slot at the same moment. Exactly one booking succeeds.'),
             'attrs': {'Test Type': 'Integration', 'Automated': 'true', 'Test Environment': 'CI/CD'}},
            {'key': 'tc_perf', 'section': '3.2', 'day': 16, 'by': 'jonas', 'status': 'draft', 'priority': 'medium',
             'text': p('Run 500 simulated users searching for slots for 10 minutes. 95% of searches return within 2 seconds.'),
             'attrs': {'Test Type': 'System', 'Automated': 'true', 'Test Environment': 'Staging'}},
            {'key': 'incident', 'section': '5.2', 'day': 5, 'by': 'jonas', 'status': 'in-review', 'priority': 'high', 'assignee': 'tom',
             'text': p('During the load test on the staging system the confirmation email arrived after 3 minutes.'), 'tags': ['Performance', 'Blocked'],
             'comments': [
                 ('tom', 4, 'The email service limits the number of messages per minute. I asked the provider to raise the limit.', []),
             ]},
        ],
    },
    {
        'key': 'asvs',
        'name': 'Booking Portal Security Review',
        'description': 'Security review of the booking pages against the OWASP Application Security Verification Standard.',
        'template': 'OWASP ASVS 5.0',
        'color': '#dc2626',
        'created_by': 'jonas',
        'day': 12,
        'members': [('tom', 'viewer', 12)],
        'items': [
            {'key': 'a_injection', 'section': '1.2', 'day': 12, 'by': 'jonas', 'status': 'approved', 'priority': 'high',
             'text': p('All database queries use parameterised statements. Checked in the code review.'),
             'attrs': {'ASVS Level': 'L1', 'Verification Result': 'Pass'}},
            {'key': 'a_validation', 'section': '2.2', 'day': 11, 'by': 'jonas', 'status': 'approved', 'priority': 'medium',
             'text': p('Phone numbers and email addresses are validated on the server.'),
             'attrs': {'ASVS Level': 'L1', 'Verification Result': 'Pass'}},
            {'key': 'a_antiauto', 'section': '2.4', 'day': 11, 'by': 'jonas', 'status': 'draft', 'priority': 'medium',
             'text': p('The booking form accepts at most five bookings per phone number per day.'),
             'attrs': {'ASVS Level': 'L2', 'Verification Result': 'Not verified'}},
            {'key': 'a_cookies', 'section': '3.3', 'day': 10, 'by': 'jonas', 'status': 'approved', 'priority': 'high',
             'text': p('Session cookies carry the Secure, HttpOnly and SameSite attributes.'),
             'attrs': {'ASVS Level': 'L1', 'Verification Result': 'Pass'}},
            {'key': 'a_headers', 'section': '3.4', 'day': 9, 'by': 'jonas', 'status': 'in-review', 'priority': 'high', 'assignee': 'jonas',
             'text': p('The booking pages send a Content-Security-Policy header.'), 'tags': ['Security'],
             'attrs': {'ASVS Level': 'L2', 'Verification Result': 'Fail'}},
        ],
    },
    {
        'key': 'arch',
        'name': 'Online Booking System Architecture',
        'description': 'Architecture of the online booking system in the arc42 structure.',
        'template': 'arc42 Architecture Documentation',
        'color': '#0891b2',
        'created_by': 'tom',
        'day': 15,
        'members': [('aisha', 'editor', 15), ('daniel', 'editor', 14), ('jonas', 'viewer', 14)],
        'items': [
            {'key': 'arc_goal', 'section': '1.2', 'day': 15, 'by': 'tom', 'status': 'draft', 'priority': 'high',
             'text': p('Quality goal: a patient completes a booking in less than two minutes.')},
            {'key': 'arc_stake', 'section': '1.3', 'day': 14, 'by': 'tom', 'status': 'draft', 'priority': 'medium',
             'text': p('Stakeholders:') + '<ul><li>Patients: book appointments.</li><li>Reception staff: manage schedules.</li><li>Clinic management: approves the system and its costs.</li></ul>'},
            {'key': 'arc_context', 'section': '3.1', 'day': 14, 'by': 'daniel', 'status': 'in-review', 'priority': 'medium',
             'text': p('The booking system exchanges data with the staff rota system, the SMS provider and the email service.')},
            {'key': 'arc_strategy', 'section': '4', 'day': 12, 'by': 'daniel', 'status': 'draft', 'priority': 'medium',
             'text': p('One web application with one relational database. A scheduled job sends the reminders every 15 minutes.')},
            {'key': 'arc_decision', 'section': '9', 'day': 10, 'by': 'tom', 'status': 'in-review', 'priority': 'medium',
             'text': p("Decision: keep the clinics' current SMS provider, so that the clinics keep one contract.")},
            {'key': 'arc_risk', 'section': '11', 'day': 9, 'by': 'aisha', 'status': 'draft', 'priority': 'high', 'assignee': 'tom',
             'text': p('Risk: the rota export runs once a day, so schedule changes made during the day reach the booking system the next morning.'),
             'tags': ['Needs Discussion']},
        ],
    },
]

LINKS = [
    ('book', 'derived-from', 'functions', 'aisha', 31),
    ('search', 'derived-from', 'functions', 'aisha', 31),
    ('double', 'related-to', 'book', 'jonas', 25),
    ('deposit', 'conflicts-with', 'scope', 'tom', 22),
    ('perf_search', 'traces-to', 'search', 'jonas', 23),
    ('book', 'verified-by', 'tc_book', 'jonas', 19),
    ('cancel', 'verified-by', 'tc_cancel_ok', 'jonas', 18),
    ('cancel', 'verified-by', 'tc_cancel_late', 'jonas', 18),
    ('double', 'verified-by', 'tc_double', 'jonas', 17),
    ('perf_search', 'verified-by', 'tc_perf', 'jonas', 16),
    ('g_retention', 'related-to', 'gdpr', 'aisha', 30),
]

SAVED_VIEWS = [
    ('tom', 'booking', 'In review', {'status': 'in-review'}),
    ('tom', 'booking', 'High priority', {'priority': 'high'}),
]


def flow_diagram():
    steps = ['Choose a service', 'Choose a free slot', 'Enter contact details', 'Confirm']
    width, height, box_width, box_height, gap = 1440, 280, 290, 130, 80
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    left = (width - len(steps) * box_width - (len(steps) - 1) * gap) // 2
    top = (height - box_height) // 2
    for index, step in enumerate(steps):
        x = left + index * (box_width + gap)
        draw.rounded_rectangle((x, top, x + box_width, top + box_height), radius=14, fill='#e8eef8', outline='#284E8A', width=3)
        draw.text((x + box_width / 2, top + box_height / 2), step, fill='#1e293b', font=font, anchor='mm')
        if index < len(steps) - 1:
            start, end, middle = x + box_width + 8, x + box_width + gap - 8, top + box_height / 2
            draw.line((start, middle, end - 10, middle), fill='#284E8A', width=4)
            draw.polygon([(end, middle), (end - 14, middle - 9), (end - 14, middle + 9)], fill='#284E8A')
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def workshop_notes():
    html = (
        '<h1 style="font-family: sans-serif; font-size: 18pt;">Requirements workshop: online booking</h1>'
        '<p style="font-family: sans-serif;">Participants: product management, business analysis, reception staff of two clinics.</p>'
        '<h2 style="font-family: sans-serif; font-size: 13pt;">Decisions</h2>'
        '<ul style="font-family: sans-serif;">'
        '<li>Patients book, move and cancel appointments online.</li>'
        '<li>Reception staff keep full control of practitioners\' schedules.</li>'
        '<li>Reminders are sent by SMS 24 hours before an appointment.</li>'
        '<li>Billing stays in the existing billing system.</li>'
        '</ul>'
    )
    return HTML(string=html).write_pdf()


ATTACHMENTS = {
    'workshop': ('requirements-workshop-notes.pdf', workshop_notes),
    'sms_texts': ('sms-reminder-texts.txt', lambda: (
        'Reminder: you have an appointment at Riverside Physio {clinic} tomorrow at {time} with {practitioner}.\n'
        'To cancel or move it, open the link in your confirmation email.\n'
    ).encode()),
    'opening_hours': ('clinic-opening-hours.csv', lambda: (
        'clinic,weekday,opens,closes\n'
        'Central,Monday-Friday,07:00,21:00\n'
        'Central,Saturday,09:00,15:00\n'
        'Harbour,Monday-Friday,08:00,20:00\n'
        'Northside,Monday-Friday,08:00,18:00\n'
        'Westpark,Monday-Saturday,09:00,17:00\n'
    ).encode()),
}

IMAGES = {
    'flow': ('booking-steps.png', flow_diagram),
}


class Command(BaseCommand):
    help = 'Fill an empty database with the demo data used for the user manual: users, projects, items and their history'

    def handle(self, *args, **options):
        if Project.objects.exists() or User.objects.exists():
            raise CommandError('The database already holds users or projects. seed_data runs only on an empty database.')
        self.now = timezone.localtime()
        self.ticks = 0
        with transaction.atomic():
            SystemSettings.load()
            self.users = self.create_users()
            self.templates = {template.name: template for template in Template.objects.filter(is_builtin=True)}
            self.create_custom_templates()
            self.items = {}
            self.projects = {}
            for event in sorted(self.events(), key=lambda event: (-event[0], event[1], event[2])):
                event[3]()
            self.finish()
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(self.users)} users, {len(self.projects)} projects and {len(self.items)} items.'
        ))

    def moment(self, days, hour):
        self.ticks += 1
        when = (self.now - timedelta(days=days)).replace(hour=hour, minute=(days * 7) % 60, second=0, microsecond=0)
        return min(when, self.now - timedelta(minutes=15)) + timedelta(seconds=self.ticks)

    def stamp(self, when, action):
        marks = {model: model.objects.aggregate(top=Max('pk'))['top'] or 0 for model in (AuditLog, ProjectVersion, Notification)}
        result = action()
        AuditLog.objects.filter(pk__gt=marks[AuditLog]).update(created_at=when)
        ProjectVersion.objects.filter(pk__gt=marks[ProjectVersion]).update(changed_at=when)
        Notification.objects.filter(pk__gt=marks[Notification]).update(created_at=when)
        return result

    def create_users(self):
        users = {}
        for data in USERS:
            user = User(
                email=data['email'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                system_role=data['system_role'],
                department=data['department'],
                avatar_color=data['avatar_color'],
                is_staff=data['system_role'] == 'admin',
                is_superuser=data['system_role'] == 'admin',
            )
            if data['key'] == 'tom':
                user.set_password(secrets.token_urlsafe(24))
            else:
                user.set_unusable_password()
            user.save()
            joined = self.moment(data['joined'], 9)
            updates = {'date_joined': joined}
            if not data.get('invited'):
                updates['last_login'] = self.moment(data.get('deactivated', 1), 8)
            if data.get('deactivated'):
                updates['is_active'] = False
            User.objects.filter(pk=user.pk).update(**updates)
            user.refresh_from_db()
            users[data['key']] = user
        return users

    def create_custom_templates(self):
        for data in CUSTOM_TEMPLATES:
            template = Template.objects.create(
                name=data['name'],
                description=data['description'],
                doc_type=data['doc_type'],
                is_global=data['is_global'],
                created_by=self.users[data['created_by']],
            )
            parents = {}
            for order, (number, title, description) in enumerate(data['sections']):
                parents[number] = TemplateSection.objects.create(
                    template=template, number=number, title=title, description=description,
                    order=order, parent=parents.get(number.rpartition('.')[0]),
                )
            for order, (name, field_type, options) in enumerate(data['attributes']):
                TemplateAttribute.objects.create(template=template, name=name, field_type=field_type, options=options, order=order)
            when = self.moment(data['day'], 11)
            Template.objects.filter(pk=template.pk).update(created_at=when, updated_at=when)

    def events(self):
        sequence = 0

        def add(days, hour, action):
            nonlocal sequence
            sequence += 1
            events.append((days, hour, sequence, action))

        events = []
        for project in PROJECTS:
            add(project['day'], 9, lambda project=project: self.create_project(project))
            for user, role, day in project['members']:
                add(day, 10, lambda project=project, user=user, role=role: self.add_member(project, user, role))
            for item in project['items']:
                add(item['day'], 11, lambda project=project, item=item: self.create_item(project, item))
                if 'attachment' in item:
                    kind, day, user = item['attachment']
                    add(day, 12, lambda item=item, kind=kind, user=user: self.attach(item, kind, user))
                for day, user, status in item.get('changes', []):
                    add(day, 14, lambda item=item, user=user, status=status: self.change_status(item, user, status))
                for author, day, text, replies in item.get('comments', []):
                    add(day, 15, lambda item=item, author=author, text=text, replies=replies: self.comment(item, author, text, replies))
            if 'archived' in project:
                add(project['archived'], 16, lambda project=project: self.archive(project))
        for source, link_type, target, user, day in LINKS:
            add(day, 13, lambda source=source, link_type=link_type, target=target, user=user: self.link(source, link_type, target, user))
        return events

    def create_project(self, data):
        when = self.moment(data['day'], 9)
        creator = self.users[data['created_by']]

        def action():
            project = Project.objects.create(
                name=data['name'],
                slug=Project.generate_unique_slug(data['name']),
                description=data['description'],
                template=self.templates[data['template']],
                status='active',
                color=data['color'],
                created_by=creator,
            )
            ProjectMembership.objects.create(project=project, user=creator, role='admin', added_by=creator)
            project.copy_template_structure()
            for name, color in PROJECT_TAGS.get(data['key'], []):
                Tag.objects.create(name=name, color=color, project=project, created_by=creator)
            return project

        project = self.stamp(when, action)
        Project.objects.filter(pk=project.pk).update(created_at=when)
        ProjectMembership.objects.filter(project=project).update(added_at=when)
        self.projects[data['key']] = project

    def add_member(self, data, user_key, role):
        project = self.projects[data['key']]
        creator = self.users[data['created_by']]
        when = self.moment(next(day for user, _, day in data['members'] if user == user_key), 10)
        membership = self.stamp(when, lambda: ProjectMembership.objects.create(
            project=project, user=self.users[user_key], role=role, added_by=creator,
        ))
        ProjectMembership.objects.filter(pk=membership.pk).update(added_at=when)

    def create_item(self, data, item_data):
        project = Project.objects.get(pk=self.projects[data['key']].pk)
        when = self.moment(item_data['day'], 11)
        section = project.sections.get(number=item_data['section'])
        author = self.users[item_data['by']]

        def action():
            item = Item(
                project=project,
                section=section,
                item_id=project.generate_item_id(),
                text=item_data['text'],
                status=item_data['status'],
                priority=item_data['priority'],
                assignee=self.users.get(item_data.get('assignee')),
                created_by=author,
                order=(section.items.aggregate(top=Max('order'))['top'] or 0) + 1,
            )
            if 'image' in item_data:
                filename, build = IMAGES[item_data['image'][0]]
                item.image.save(filename, ContentFile(build()), save=False)
                item.image_caption = item_data['image'][1]
            item._actor = author
            item.save()
            Project.objects.filter(pk=project.pk).update(next_item_number=project.next_item_number + 1)
            attributes = {attribute.name: attribute for attribute in project.attributes.all()}
            for name, value in item_data.get('attrs', {}).items():
                ItemAttributeValue.objects.create(item=item, attribute=attributes[name], value=value)
            for name in item_data.get('tags', []):
                ItemTag.objects.create(item=item, tag=Tag.for_project(project).get(name=name))
            return item

        item = self.stamp(when, action)
        Item.objects.filter(pk=item.pk).update(created_at=when, updated_at=when)
        self.items[item_data['key']] = item

    def change_status(self, item_data, user_key, status):
        item = Item.objects.get(pk=self.items[item_data['key']].pk)
        when = self.moment(next(day for day, user, value in item_data['changes'] if user == user_key and value == status), 14)
        item.status = status
        item._actor = self.users[user_key]
        self.stamp(when, item.save)
        Item.objects.filter(pk=item.pk).update(updated_at=when)

    def comment(self, item_data, author_key, text, replies):
        item = self.items[item_data['key']]
        day = next(day for author, day, value, _ in item_data['comments'] if author == author_key and value == text)
        when = self.moment(day, 15)
        parent = self.stamp(when, lambda: Comment.objects.create(item=item, author=self.users[author_key], text=text))
        Comment.objects.filter(pk=parent.pk).update(created_at=when)
        for reply_author, reply_day, reply_text in replies:
            reply_when = self.moment(reply_day, 16)
            reply = self.stamp(reply_when, lambda: Comment.objects.create(
                item=item, author=self.users[reply_author], text=reply_text, parent=parent,
            ))
            Comment.objects.filter(pk=reply.pk).update(created_at=reply_when)

    def attach(self, item_data, kind, user_key):
        item = self.items[item_data['key']]
        when = self.moment(item_data['attachment'][1], 12)
        filename, build = ATTACHMENTS[kind]
        content = build()
        user = self.users[user_key]

        def action():
            attachment = Attachment(item=item, filename=filename, file_size=len(content), uploaded_by=user)
            attachment.file.save(filename, ContentFile(content), save=False)
            attachment.save()
            AuditLog.objects.create(
                project=item.project, user=user, action='attachment_added',
                target_type='Item', target_id=item.item_id, details={'filename': filename},
            )
            return attachment

        attachment = self.stamp(when, action)
        Attachment.objects.filter(pk=attachment.pk).update(uploaded_at=when)

    def link(self, source_key, link_type, target_key, user_key):
        source, target = self.items[source_key], self.items[target_key]
        user = self.users[user_key]
        when = self.moment(next(day for s, t, g, u, day in LINKS if (s, t, g) == (source_key, link_type, target_key)), 13)

        def action():
            link = TraceabilityLink.objects.create(source_item=source, target_item=target, link_type=link_type, created_by=user)
            AuditLog.objects.create(
                project=source.project, user=user, action='link_added',
                target_type='Item', target_id=source.item_id,
                details={'link_type': link_type, 'target': target.item_id},
            )
            return link

        link = self.stamp(when, action)
        TraceabilityLink.objects.filter(pk=link.pk).update(created_at=when)

    def archive(self, data):
        when = self.moment(data['archived'], 16)
        Project.objects.filter(pk=self.projects[data['key']].pk).update(status='archived', archived_at=when)

    def finish(self):
        statuses = {
            'gdpr': 'active', 'booking': 'active', 'testplan': 'in-review', 'asvs': 'in-review', 'arch': 'draft',
        }
        for key, project in self.projects.items():
            project.refresh_from_db()
            times = list(AuditLog.objects.filter(project=project).values_list('created_at', flat=True))
            times += [value for value in (project.created_at, project.archived_at) if value]
            updates = {'updated_at': max(times)}
            if key in statuses:
                updates['status'] = statuses[key]
            Project.objects.filter(pk=project.pk).update(**updates)
        for user_key, project_key, name, filters in SAVED_VIEWS:
            SavedView.objects.create(project=self.projects[project_key], user=self.users[user_key], name=name, filters=filters)
        recent = self.now - timedelta(days=3)
        Notification.objects.filter(created_at__lt=recent).update(is_read=True, pushed_at=recent)
        Notification.objects.filter(created_at__gte=recent).update(pushed_at=self.now)
