import os
if os.path.exists("tracker.db"):
    os.remove("tracker.db")

from app import app, init_db
init_db()

with app.test_client(use_cookies=True) as c:
    # Register & login
    c.post('/register', data={'username': 'alice', 'password': 'pass', 'confirm_password': 'pass'})

    # Create project + members
    c.post('/create_project', data={'project_name': 'DBMS Mini Project'})
    c.post('/project/1/add_member', data={'member_name': 'Ravi'})
    c.post('/project/1/add_member', data={'member_name': 'Priya'})
    c.post('/project/1/add_member', data={'member_name': 'Kiran'})

    # Ravi: 4 tasks, all complete  (task ids 1-4)
    for t in ['T1', 'T2', 'T3', 'T4']:
        c.post('/project/1/assign_task', data={'task_title': t, 'member_id': '1'})
    for tid in [1, 2, 3, 4]:
        c.post(f'/task/{tid}/complete')

    # Priya: 4 tasks, 2 complete  (task ids 5-8)
    for t in ['T5', 'T6', 'T7', 'T8']:
        c.post('/project/1/assign_task', data={'task_title': t, 'member_id': '2'})
    c.post('/task/5/complete')
    c.post('/task/6/complete')

    # Kiran: 2 tasks, none complete  (task ids 9-10)
    c.post('/project/1/assign_task', data={'task_title': 'T9',  'member_id': '3'})
    c.post('/project/1/assign_task', data={'task_title': 'T10', 'member_id': '3'})

    r = c.get('/project/1/summary')
    assert r.status_code == 200, f"Expected 200 got {r.status_code}"
    html = r.data.decode()

    checks = {
        'Overall Project Progress': 'Overall progress section',
        'Total Tasks':              'Total tasks label',
        'Individual Contributions': 'Individual contributions table heading',
        'Contribution %':           'Contribution % column header',
        'Ravi':                     'Ravi row',
        'Priya':                    'Priya row',
        'Kiran':                    'Kiran row',
        '100%':                     'Ravi 100% contribution',
        '50%':                      'Priya 50% contribution',
        '0%':                       'Kiran 0% contribution',
        'Back to Project':          'Back to Project button',
        'Home':                     'Home button',
    }

    all_pass = True
    for text, label in checks.items():
        found = text in html
        status = "OK  " if found else "FAIL"
        print(f"  {status}  {label}")
        if not found:
            all_pass = False

    assert all_pass, "One or more checks failed."

print("\nAll Module 3 spec checks passed.")
