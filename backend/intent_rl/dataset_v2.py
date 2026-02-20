"""Intent RL Dataset v2 — Real fragmented human speech with complex intents.

Each test case simulates a REAL user speaking to MyndLens in broken thoughts:
- One MAIN INTENT (the overarching goal)
- Multiple BROKEN THOUGHTS (fragments that together form the mandate)
- SUB-INTENTS embedded within the fragments
- Ambiguous references that the Digital Self should resolve

The L1 Scout must:
1. Identify the MAIN INTENT correctly
2. Extract the key sub-intents / dimensions
3. Use Digital Self to resolve ambiguous references
"""

INTENT_DATASET_V2 = [
    # ── 1. TRAVEL CONCIERGE ──────────────────────────────────────────────
    {
        "id": 1,
        "main_intent": "Travel Concierge",
        "broken_thoughts": "Need to go to Sydney. Next week. For the conference. Will return after 10 days. Hotel and car needed. Need to meet Alex there too.",
        "sub_intents": ["book_flight", "book_hotel", "rent_car", "schedule_meeting"],
        "expected_entities": ["Sydney", "Alex"],
        "expected_dimensions": {"where": "Sydney", "when": "next week", "duration": "10 days"},
    },
    {
        "id": 2,
        "main_intent": "Travel Concierge",
        "broken_thoughts": "Tokyo trip in March. Business class if possible. Need the usual hotel near Shibuya. Oh and arrange a dinner with the Tokyo team.",
        "sub_intents": ["book_flight", "book_hotel", "arrange_dinner"],
        "expected_entities": ["Tokyo"],
        "expected_dimensions": {"where": "Tokyo", "when": "March", "how": "business class"},
    },
    {
        "id": 3,
        "main_intent": "Travel Concierge",
        "broken_thoughts": "Quick trip to London. Just two nights. No car needed the tube is fine. But book something near the office. Oh and check if Sarah is in town that week.",
        "sub_intents": ["book_flight", "book_hotel", "check_availability"],
        "expected_entities": ["London", "Sarah"],
        "expected_dimensions": {"where": "London", "duration": "2 nights"},
    },

    # ── 2. EVENT PLANNING ────────────────────────────────────────────────
    {
        "id": 4,
        "main_intent": "Event Planning",
        "broken_thoughts": "Team offsite next month. Maybe 20 people. Need a venue with AV setup. Catering for two days. Budget around 5k. Lisa should handle the agenda.",
        "sub_intents": ["find_venue", "arrange_catering", "set_budget", "delegate_task"],
        "expected_entities": ["Lisa"],
        "expected_dimensions": {"what": "team offsite", "when": "next month", "how_many": "20"},
    },
    {
        "id": 5,
        "main_intent": "Event Planning",
        "broken_thoughts": "Sarah's birthday is coming up. Surprise party maybe? At that Italian place. Invite the whole team. And get a cake. Don't tell her obviously.",
        "sub_intents": ["book_restaurant", "send_invitations", "order_cake", "keep_secret"],
        "expected_entities": ["Sarah"],
        "expected_dimensions": {"what": "surprise birthday party", "where": "Italian restaurant"},
    },
    {
        "id": 6,
        "main_intent": "Event Planning",
        "broken_thoughts": "Product launch event in two weeks. Need to send invites to press list. Book the rooftop space. Get the demo ready. Mike handles the tech setup.",
        "sub_intents": ["send_invitations", "book_venue", "prepare_demo", "delegate_task"],
        "expected_entities": ["Mike"],
        "expected_dimensions": {"what": "product launch", "when": "two weeks"},
    },

    # ── 3. PROJECT KICKOFF ───────────────────────────────────────────────
    {
        "id": 7,
        "main_intent": "Project Kickoff",
        "broken_thoughts": "New project starting. Need to set up the repo. Create the Jira board. Schedule the kickoff meeting. Get Bob and Lisa and Mike on it. Two week sprints.",
        "sub_intents": ["create_repository", "create_project_board", "schedule_meeting", "assign_team"],
        "expected_entities": ["Bob", "Lisa", "Mike"],
        "expected_dimensions": {"what": "new project", "who": "Bob, Lisa, Mike"},
    },
    {
        "id": 8,
        "main_intent": "Project Kickoff",
        "broken_thoughts": "The Johnson proposal got approved. Time to kick it off. Need a timeline. Assign the frontend to Lisa backend to Mike. First sprint starts Monday.",
        "sub_intents": ["create_timeline", "assign_tasks", "schedule_sprint"],
        "expected_entities": ["Johnson", "Lisa", "Mike"],
        "expected_dimensions": {"what": "Johnson project kickoff", "when": "Monday"},
    },

    # ── 4. HIRING PIPELINE ───────────────────────────────────────────────
    {
        "id": 9,
        "main_intent": "Hiring Pipeline",
        "broken_thoughts": "We need to hire two more devs. Senior level. Post on LinkedIn and our careers page. Sarah should screen resumes. Budget up to 150k per head.",
        "sub_intents": ["post_job_listing", "delegate_screening", "set_budget"],
        "expected_entities": ["Sarah"],
        "expected_dimensions": {"what": "hire senior developers", "how_many": "2"},
    },
    {
        "id": 10,
        "main_intent": "Hiring Pipeline",
        "broken_thoughts": "That candidate from the conference follow up with them. Schedule a tech interview with Mike. If they pass send the offer letter. Check their references too.",
        "sub_intents": ["follow_up_contact", "schedule_interview", "prepare_offer", "check_references"],
        "expected_entities": ["Mike"],
        "expected_dimensions": {"what": "candidate pipeline"},
    },

    # ── 5. FINANCIAL OPERATIONS ──────────────────────────────────────────
    {
        "id": 11,
        "main_intent": "Financial Operations",
        "broken_thoughts": "End of month coming up. Need to process all pending invoices. Pay the AWS bill. Submit expense reports. Bob needs the Q3 budget numbers by Friday.",
        "sub_intents": ["process_invoices", "pay_bill", "submit_expenses", "prepare_report"],
        "expected_entities": ["Bob"],
        "expected_dimensions": {"when": "end of month", "deadline": "Friday"},
    },
    {
        "id": 12,
        "main_intent": "Financial Operations",
        "broken_thoughts": "The subscription costs are out of control. Cancel Netflix and the unused Figma seats. Downgrade Slack to the free tier. Get me a total of what we save.",
        "sub_intents": ["cancel_subscription", "downgrade_service", "calculate_savings"],
        "expected_entities": [],
        "expected_dimensions": {"what": "cost reduction"},
    },
    {
        "id": 13,
        "main_intent": "Financial Operations",
        "broken_thoughts": "Client wants a revised quote. Lower it by 15 percent. Include the maintenance package this time. Send it before their board meeting Thursday.",
        "sub_intents": ["revise_quote", "add_package", "send_document"],
        "expected_entities": [],
        "expected_dimensions": {"what": "revised quote", "deadline": "Thursday"},
    },

    # ── 6. CONTENT CREATION ──────────────────────────────────────────────
    {
        "id": 14,
        "main_intent": "Content Creation",
        "broken_thoughts": "Need a blog post about our new feature. Include screenshots. Make it SEO friendly. Post it on our site and share on LinkedIn and Twitter. Jess should review before publishing.",
        "sub_intents": ["write_blog_post", "add_screenshots", "optimize_seo", "publish", "share_social", "get_review"],
        "expected_entities": ["Jess"],
        "expected_dimensions": {"what": "blog post about new feature"},
    },
    {
        "id": 15,
        "main_intent": "Content Creation",
        "broken_thoughts": "Quarterly newsletter time. Pull highlights from the last 3 months. Include the team photo from the offsite. Add a section about upcoming product changes. Email to subscriber list by Monday.",
        "sub_intents": ["compile_highlights", "add_photos", "write_section", "send_newsletter"],
        "expected_entities": [],
        "expected_dimensions": {"what": "quarterly newsletter", "deadline": "Monday"},
    },
    {
        "id": 16,
        "main_intent": "Content Creation",
        "broken_thoughts": "Write an apology email to the customer about the outage. Explain what happened. What we fixed. The compensation offer. Run it by Sarah before sending.",
        "sub_intents": ["draft_email", "include_explanation", "add_compensation", "get_approval"],
        "expected_entities": ["Sarah"],
        "expected_dimensions": {"what": "customer apology about outage"},
    },

    # ── 7. CUSTOMER SUCCESS ──────────────────────────────────────────────
    {
        "id": 17,
        "main_intent": "Customer Success",
        "broken_thoughts": "Johnson account is at risk. They haven't logged in for 2 weeks. Schedule a check-in call. Prepare a usage report. Maybe offer them the premium features free for a month.",
        "sub_intents": ["schedule_call", "prepare_report", "create_offer"],
        "expected_entities": ["Johnson"],
        "expected_dimensions": {"what": "at-risk customer retention"},
    },
    {
        "id": 18,
        "main_intent": "Customer Success",
        "broken_thoughts": "New enterprise client onboarding. Need to set up their workspace. Import their data. Schedule training sessions. Assign Jess as their account manager.",
        "sub_intents": ["setup_workspace", "import_data", "schedule_training", "assign_manager"],
        "expected_entities": ["Jess"],
        "expected_dimensions": {"what": "enterprise client onboarding"},
    },

    # ── 8. PERSONAL WELLNESS ─────────────────────────────────────────────
    {
        "id": 19,
        "main_intent": "Personal Wellness",
        "broken_thoughts": "I need to get back in shape. Book a gym session for tomorrow morning. Set a daily reminder for stretching at 7am. Find a meal prep service that delivers. Also schedule that doctor appointment I keep putting off.",
        "sub_intents": ["book_gym", "set_reminder", "find_service", "schedule_appointment"],
        "expected_entities": [],
        "expected_dimensions": {"what": "health and wellness plan"},
    },
    {
        "id": 20,
        "main_intent": "Personal Wellness",
        "broken_thoughts": "Feeling burned out. Block off next Friday completely. No meetings. Reschedule anything that's on the calendar. Maybe plan a day trip somewhere quiet.",
        "sub_intents": ["block_calendar", "reschedule_meetings", "plan_trip"],
        "expected_entities": [],
        "expected_dimensions": {"what": "burnout recovery day", "when": "next Friday"},
    },

    # ── 9. DATA & ANALYTICS ──────────────────────────────────────────────
    {
        "id": 21,
        "main_intent": "Data & Analytics",
        "broken_thoughts": "Board meeting next week. Need a dashboard showing revenue growth. Churn rate trend. Customer acquisition cost. Compare this quarter vs last. Make it look good.",
        "sub_intents": ["create_dashboard", "add_revenue_chart", "add_churn_chart", "add_cac_chart", "quarterly_comparison"],
        "expected_entities": [],
        "expected_dimensions": {"what": "board meeting dashboard", "when": "next week"},
    },
    {
        "id": 22,
        "main_intent": "Data & Analytics",
        "broken_thoughts": "Something's wrong with the funnel. Check where users are dropping off. Compare signup to activation rates. Look at the last 30 days. Get Mike to check the technical side.",
        "sub_intents": ["analyze_funnel", "compare_rates", "investigate_technical"],
        "expected_entities": ["Mike"],
        "expected_dimensions": {"what": "funnel analysis", "timeframe": "30 days"},
    },

    # ── 10. OPERATIONS / INCIDENT ────────────────────────────────────────
    {
        "id": 23,
        "main_intent": "Incident Response",
        "broken_thoughts": "Server is down. Page the on-call team. Check the logs. Notify affected customers. Set up a war room call in 10 minutes. Mike leads the investigation.",
        "sub_intents": ["page_team", "check_logs", "notify_customers", "setup_call", "assign_lead"],
        "expected_entities": ["Mike"],
        "expected_dimensions": {"what": "server outage", "urgency": "immediate"},
    },
    {
        "id": 24,
        "main_intent": "Incident Response",
        "broken_thoughts": "Data breach suspected. Lock down the affected accounts. Notify legal. Start forensic analysis. Prepare customer notification draft. This is top priority everything else stops.",
        "sub_intents": ["lock_accounts", "notify_legal", "start_forensics", "draft_notification"],
        "expected_entities": [],
        "expected_dimensions": {"what": "data breach response", "urgency": "critical"},
    },

    # ── 11. WEEKLY PLANNING ──────────────────────────────────────────────
    {
        "id": 25,
        "main_intent": "Weekly Planning",
        "broken_thoughts": "Let me plan the week. Monday I have the standup and 1-on-1 with Lisa. Tuesday clear for deep work. Wednesday team sync. Thursday client calls. Friday wrap up and send the status report to Sarah.",
        "sub_intents": ["organize_calendar", "block_deep_work", "prepare_report"],
        "expected_entities": ["Lisa", "Sarah"],
        "expected_dimensions": {"what": "weekly schedule planning"},
    },
    {
        "id": 26,
        "main_intent": "Weekly Planning",
        "broken_thoughts": "Sprint planning for next week. Pull in the top backlog items. Assign stories to the team. Check capacity since Bob is on vacation. Deadline for the API is Thursday.",
        "sub_intents": ["plan_sprint", "assign_stories", "check_capacity"],
        "expected_entities": ["Bob"],
        "expected_dimensions": {"what": "sprint planning", "deadline": "Thursday"},
    },

    # ── 12. REAL ESTATE / RELOCATION ─────────────────────────────────────
    {
        "id": 27,
        "main_intent": "Relocation Planning",
        "broken_thoughts": "Lease is up in September. Start looking for a new office. Need at least 3000 sq ft. Close to the subway. Budget 8k a month. Schedule tours for next week.",
        "sub_intents": ["search_properties", "schedule_tours", "set_criteria"],
        "expected_entities": [],
        "expected_dimensions": {"what": "office relocation", "when": "September", "budget": "8k/month"},
    },

    # ── 13. MARKETING CAMPAIGN ───────────────────────────────────────────
    {
        "id": 28,
        "main_intent": "Marketing Campaign",
        "broken_thoughts": "Launch campaign for the new feature. Email blast to existing users. Social media posts on all platforms. Set up Google Ads with 2k budget. Landing page needs updating. Track conversion rates.",
        "sub_intents": ["send_email_blast", "post_social_media", "setup_ads", "update_landing_page", "setup_tracking"],
        "expected_entities": [],
        "expected_dimensions": {"what": "new feature launch campaign", "budget": "2k"},
    },
    {
        "id": 29,
        "main_intent": "Marketing Campaign",
        "broken_thoughts": "Webinar next Thursday. Set up the Zoom link. Create the registration page. Email invites to the prospect list. Prepare the slide deck. Jess moderates, I present.",
        "sub_intents": ["setup_webinar", "create_registration", "send_invites", "prepare_slides", "assign_roles"],
        "expected_entities": ["Jess"],
        "expected_dimensions": {"what": "webinar", "when": "next Thursday"},
    },

    # ── 14. VENDOR MANAGEMENT ────────────────────────────────────────────
    {
        "id": 30,
        "main_intent": "Vendor Management",
        "broken_thoughts": "Need to switch cloud providers. Get quotes from AWS GCP and Azure. Compare pricing for our usage. Schedule calls with their sales teams. Decision by end of month.",
        "sub_intents": ["request_quotes", "compare_pricing", "schedule_calls"],
        "expected_entities": [],
        "expected_dimensions": {"what": "cloud provider evaluation", "deadline": "end of month"},
    },

    # ── 15. AUTOMATION SETUP ─────────────────────────────────────────────
    {
        "id": 31,
        "main_intent": "Automation Setup",
        "broken_thoughts": "I'm tired of doing this manually every week. When a new lead comes in auto-assign to the right rep based on region. Send them the welcome pack. Log it in the CRM. Notify me only for enterprise leads.",
        "sub_intents": ["create_auto_assignment", "setup_welcome_email", "crm_integration", "conditional_notification"],
        "expected_entities": [],
        "expected_dimensions": {"what": "lead routing automation"},
    },
    {
        "id": 32,
        "main_intent": "Automation Setup",
        "broken_thoughts": "Every Friday at 5pm compile the team's weekly updates into one report. Email it to Sarah. Save a copy in the shared drive. If anyone missed their update ping them Thursday afternoon.",
        "sub_intents": ["schedule_compilation", "send_report", "save_backup", "setup_reminder"],
        "expected_entities": ["Sarah"],
        "expected_dimensions": {"what": "weekly report automation", "when": "Friday 5pm"},
    },

    # ── 16. CONFLICT RESOLUTION ──────────────────────────────────────────
    {
        "id": 33,
        "main_intent": "Conflict Resolution",
        "broken_thoughts": "Bob and Lisa are not getting along on the project. Need to schedule a mediation meeting. Review the history of what happened. Prepare talking points. Maybe reassign some tasks to reduce friction.",
        "sub_intents": ["schedule_mediation", "review_history", "prepare_talking_points", "reassign_tasks"],
        "expected_entities": ["Bob", "Lisa"],
        "expected_dimensions": {"what": "team conflict resolution"},
    },

    # ── 17. PRODUCT LAUNCH ───────────────────────────────────────────────
    {
        "id": 34,
        "main_intent": "Product Launch",
        "broken_thoughts": "Feature is ready for release. Need the changelog written. Update the docs. Email customers about it. Set up feature flags for gradual rollout. Monitor error rates after launch.",
        "sub_intents": ["write_changelog", "update_docs", "send_announcement", "configure_feature_flags", "setup_monitoring"],
        "expected_entities": [],
        "expected_dimensions": {"what": "feature release"},
    },
    {
        "id": 35,
        "main_intent": "Product Launch",
        "broken_thoughts": "Mobile app version 2.0 goes live Monday. Submit to App Store and Play Store. Prepare the what's new text. Coordinate with marketing for the press release. Mike does the final QA pass.",
        "sub_intents": ["submit_app_stores", "write_release_notes", "coordinate_press", "assign_qa"],
        "expected_entities": ["Mike"],
        "expected_dimensions": {"what": "mobile app 2.0 launch", "when": "Monday"},
    },

    # ── 18. KNOWLEDGE MANAGEMENT ─────────────────────────────────────────
    {
        "id": 36,
        "main_intent": "Knowledge Management",
        "broken_thoughts": "Our wiki is a mess. Need to reorganize the engineering docs. Archive the outdated stuff. Create templates for new docs. Assign each team to own their section. Review quarterly.",
        "sub_intents": ["reorganize_docs", "archive_old", "create_templates", "assign_ownership", "schedule_reviews"],
        "expected_entities": [],
        "expected_dimensions": {"what": "documentation overhaul"},
    },

    # ── 19. PERSONAL FINANCE ─────────────────────────────────────────────
    {
        "id": 37,
        "main_intent": "Personal Finance",
        "broken_thoughts": "Tax season coming up. Gather all receipts. Calculate deductions. Schedule appointment with accountant. Transfer the estimated amount to savings. Check if I need to file quarterly.",
        "sub_intents": ["gather_receipts", "calculate_deductions", "schedule_appointment", "transfer_funds", "check_deadlines"],
        "expected_entities": [],
        "expected_dimensions": {"what": "tax preparation"},
    },
    {
        "id": 38,
        "main_intent": "Personal Finance",
        "broken_thoughts": "Need to sort out the budget. What are we spending on subscriptions total. Cancel anything under 10 dollars that nobody uses. Set up a shared tracker for the team expenses.",
        "sub_intents": ["audit_subscriptions", "cancel_unused", "setup_expense_tracker"],
        "expected_entities": [],
        "expected_dimensions": {"what": "subscription and budget audit"},
    },

    # ── 20. MENTORSHIP / DEVELOPMENT ─────────────────────────────────────
    {
        "id": 39,
        "main_intent": "Team Development",
        "broken_thoughts": "Lisa wants to grow into a lead role. Set up bi-weekly mentorship sessions. Find her a conference to attend. Give her ownership of the next sprint. Review her progress in 3 months.",
        "sub_intents": ["schedule_mentorship", "find_conference", "delegate_ownership", "schedule_review"],
        "expected_entities": ["Lisa"],
        "expected_dimensions": {"what": "career development plan for Lisa"},
    },
    {
        "id": 40,
        "main_intent": "Team Development",
        "broken_thoughts": "Team skills are getting stale. Find online courses for the new framework. Budget 500 per person. Give everyone a learning day every two weeks. Track completion.",
        "sub_intents": ["find_courses", "set_budget", "schedule_learning_days", "setup_tracking"],
        "expected_entities": [],
        "expected_dimensions": {"what": "team upskilling program", "budget": "500/person"},
    },
]

# All main intent categories
MAIN_INTENTS = sorted(set(d["main_intent"] for d in INTENT_DATASET_V2))
