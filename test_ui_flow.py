from fastapi.testclient import TestClient
from server import app


def test_customer_endpoints_are_available():
    client = TestClient(app)

    menu_response = client.get('/menu')
    assert menu_response.status_code == 200
    body = menu_response.json()
    assert 'menu' in body
    assert len(body['menu']) > 0

    summary_response = client.get('/summary')
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert 'total_orders' in summary
    assert 'pending_orders' in summary
    assert 'approved_orders' in summary
    assert 'low_stock_count' in summary
    assert 'low_stock_items' in summary


def test_admin_menu_management_endpoints():
    client = TestClient(app)

    add_response = client.post('/admin/menu/add', json={
        'name': 'Spicy Wings',
        'price': 180,
        'stock': 12
    })
    assert add_response.status_code == 200
    added = add_response.json()
    assert added['success'] is True

    update_response = client.post('/admin/menu/update', json={
        'item_id': added['item_id'],
        'name': 'Spicy Wings Deluxe',
        'price': 220,
        'stock': 15
    })
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated['success'] is True
