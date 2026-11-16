-- =====================================================================
-- Migration 002: starter FAQs for the help chat.
--
-- Run this ONCE in the Supabase SQL Editor if you already ran migration 001.
-- Projects created by that migration (e.g. "Default Project") had an empty
-- FAQ, so the help chat could not answer any question.
--
-- Safe to re-run: it only fills projects that have no FAQs at all.
-- (Admins can also click "Add starter FAQs" on the Help Center page.)
-- =====================================================================

-- Starter FAQs for every project that has none, so the help chat can answer
-- straight away. Projects that already have FAQs are left alone.
insert into faqs (project_id, question, answer, keywords, hits)
select p.id, d.question, d.answer, d.keywords, 0
from projects p
cross join (values
        ('How do I report a bug?', 'Testers can click ''Create Bug'' in the sidebar. Give it a clear title, the steps to reproduce, what you expected and what actually happened, then pick a priority and severity.', 'report create new submit add file log'),
        ('Why can''t I see some bugs?', 'Developers only see bugs that are assigned to them. Testers and admins see every bug in the project.', 'see missing hidden visible list developer'),
        ('How do I change a bug''s status?', 'Open the bug and use the buttons in the Status panel. Each role can only make its own moves: developers start and resolve work, testers close or reopen resolved bugs.', 'status change move workflow progress resolve'),
        ('How do I reopen a bug that isn''t really fixed?', 'When a bug is Resolved, a tester can click ''Reopen''. It goes back to the developer as Reopened. Add a comment explaining what still fails.', 'reopen fixed again broken still fail verify'),
        ('Can I reopen a closed bug?', 'No. Closed is the final state, meaning a tester verified the fix. If the problem comes back, report a new bug and mention the old bug''s ID (for example #1a2b3c4d) in the description.', 'closed reopen final undo'),
        ('How do I become a developer or admin?', 'Everyone joins a project as a Tester. Your project admin can change your role on the Users page. To run your own project, register with ''Request admin access'' and the owners will review it.', 'role developer admin promote permission become change'),
        ('How do I invite my team?', 'Admins can find the project''s invite code on the Dashboard. Teammates enter it when they register. You can regenerate the code at any time if it was shared by mistake.', 'invite code join team member add project'),
        ('How do I turn off email notifications?', 'Go to Settings and switch off ''Email notifications''. You will still see notifications in the app.', 'email notifications turn off stop unsubscribe settings'),
        ('Who do I contact if I''m stuck?', 'Type your question in this chat. If there is no answer here, send it to your project admin and you''ll get a notification when they reply.', 'contact help support admin stuck question')
    ) as d(question, answer, keywords)
where not exists (select 1 from faqs f where f.project_id = p.id);

select p.name, count(f.id) as faq_count from projects p left join faqs f on f.project_id = p.id group by p.name;
