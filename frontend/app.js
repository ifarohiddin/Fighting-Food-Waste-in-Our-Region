const API_URL = 'http://localhost:8000';

// Auth sahifasi logikasi
if (document.getElementById('auth')) {
    const authForm = document.getElementById('auth');
    const toggleAuth = document.getElementById('toggle-auth');
    const formTitle = document.getElementById('form-title');
    let isLogin = true;

    toggleAuth.addEventListener('click', () => {
        isLogin = !isLogin;
        formTitle.textContent = isLogin ? 'Login' : 'Register';
        toggleAuth.textContent = isLogin ? "Don't have an account? Register" : 'Already have an account? Login';
        document.getElementById('username').style.display = isLogin ? 'none' : 'block';
        document.getElementById('role').style.display = isLogin ? 'none' : 'block';
    });

    authForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;

        if (isLogin) {
            const response = await fetch(`${API_URL}/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ username: email, password })
            });
            const data = await response.json();
            if (response.ok) {
                localStorage.setItem('token', data.access_token);
                const user = await getCurrentUser();
                window.location.href = user.role === 'shop' ? 'shop.html' : 'customer.html';
            } else {
                alert(data.detail || 'Login failed');
            }
        } else {
            const username = document.getElementById('username').value;
            const role = document.getElementById('role').value;
            const response = await fetch(`${API_URL}/users/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, password, role })
            });
            if (response.ok) {
                alert('Registration successful! Please login.');
                toggleAuth.click();
            } else {
                const data = await response.json();
                alert(data.detail || 'Registration failed');
            }
        }
    });
}

// Foydalanuvchi ma'lumotlarini olish
async function getCurrentUser() {
    const token = localStorage.getItem('token');
    const response = await fetch(`${API_URL}/users/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return await response.json();
}

// Shop sahifasi logikasi
if (document.getElementById('bag-form')) {
    const bagForm = document.getElementById('bag-form');
    const shopBags = document.getElementById('shop-bags');
    const user = await getCurrentUser();

    bagForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const bag = {
            description: document.getElementById('description').value,
            original_price: parseFloat(document.getElementById('original_price').value),
            discounted_price: parseFloat(document.getElementById('discounted_price').value),
            quantity: parseInt(document.getElementById('quantity').value),
            pickup_time: document.getElementById('pickup_time').value
        };
        const response = await fetch(`${API_URL}/shops/${user.id}/bags`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(bag)
        });
        if (response.ok) {
            alert('Bag added successfully!');
            loadShopBags();
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to add bag');
        }
    });

    async function loadShopBags() {
        const response = await fetch(`${API_URL}/shops/${user.id}/bags`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        const bags = await response.json();
        shopBags.innerHTML = bags.map(bag => `
            <div class="bag-item">
                <p>${bag.description} - $${bag.discounted_price} (Original: $${bag.original_price})</p>
                <p>Quantity: ${bag.quantity} | Pickup: ${bag.pickup_time} | Status: ${bag.status}</p>
            </div>
        `).join('');
    }
    loadShopBags();
}

// Customer sahifasi logikasi
if (document.getElementById('available-bags')) {
    const availableBags = document.getElementById('available-bags');
    const customerOrders = document.getElementById('customer-orders');
    const user = await getCurrentUser();

    async function loadAvailableBags() {
        const response = await fetch(`${API_URL}/bags`);
        const bags = await response.json();
        availableBags.innerHTML = bags.map(bag => `
            <div class="bag-item">
                <p>${bag.description} - $${bag.discounted_price} (Original: $${bag.original_price})</p>
                <p>Quantity: ${bag.quantity} | Pickup: ${bag.pickup_time}</p>
                <button onclick="buyBag(${bag.id})">Buy Now</button>
            </div>
        `).join('');
    }

    async function loadOrders() {
        const response = await fetch(`${API_URL}/customers/${user.id}/orders`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        const orders = await response.json();
        customerOrders.innerHTML = orders.map(order => `
            <div class="bag-item">
                <p>Bag ID: ${order.bag_id} | Ordered: ${order.order_time} | Status: ${order.status}</p>
                ${order.status === 'pending' ? `<button onclick="confirmPickup(${order.bag_id})">Confirm Pickup</button>` : ''}
            </div>
        `).join('');
    }

    window.buyBag = async (bagId) => {
        const response = await fetch(`${API_URL}/customers/${user.id}/buy/${bagId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (response.ok) {
            alert('Bag purchased successfully!');
            loadAvailableBags();
            loadOrders();
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to buy bag');
        }
    };

    window.confirmPickup = async (bagId) => {
        const response = await fetch(`${API_URL}/bags/${bagId}/pickup`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (response.ok) {
            alert('Pickup confirmed!');
            loadOrders();
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to confirm pickup');
        }
    };

    loadAvailableBags();
    loadOrders();
}

// Logout logikasi
document.querySelectorAll('#logout').forEach(btn => {
    btn.addEventListener('click', () => {
        localStorage.removeItem('token');
        window.location.href = 'index.html';
    });
});