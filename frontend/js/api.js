const API_BASE = '/api/v1';

function getHeaders() {
  const token = localStorage.getItem('bbl_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

const api = {
  async getPlants() { return (await fetch(`${API_BASE}/plants`, { headers: getHeaders() })).json(); },
  async getRealtime(id = 1) { return (await fetch(`${API_BASE}/realtime/${id}`, { headers: getHeaders() })).json(); },
  async getHistory(id = 1, hours = 24) { return (await fetch(`${API_BASE}/history/${id}?hours=${hours}`, { headers: getHeaders() })).json(); },
  async getDailySummary(id = 1, date = null) { return (await fetch(`${API_BASE}/daily-summary/${id}${date ? `?date=${date}` : ''}`, { headers: getHeaders() })).json(); },
  async getAlerts(status = 'all', limit = 20) { return (await fetch(`${API_BASE}/alerts?status=${status}&limit=${limit}`, { headers: getHeaders() })).json(); },
  async getInvoices() { return (await fetch(`${API_BASE}/invoices`, { headers: getHeaders() })).json(); },
  async createInvoice(data) {
    return (await fetch(`${API_BASE}/invoices`, {
      method: 'POST', headers: getHeaders(), body: JSON.stringify(data)
    })).json();
  },
  async getDailyReports(limit = 30) { return (await fetch(`${API_BASE}/daily-reports?limit=${limit}`, { headers: getHeaders() })).json(); },
  async getSettings() { return (await fetch(`${API_BASE}/settings`, { headers: getHeaders() })).json(); },
  async updateSetting(key, value) {
    return (await fetch(`${API_BASE}/settings/${key}`, {
      method: 'PUT', headers: getHeaders(), body: JSON.stringify({ value: String(value) })
    })).json();
  },
  async getSavings(plantId, period = 'month') {
    return (await fetch(`${API_BASE}/savings/${plantId}?period=${period}`, { headers: getHeaders() })).json();
  },
  async getVapidKey() { return (await fetch(`${API_BASE}/push/vapid-key`)).json(); },
  async subscribePush(subscription) {
    return (await fetch(`${API_BASE}/push/subscribe`, {
      method: 'POST', headers: getHeaders(), body: JSON.stringify({ subscription })
    })).json();
  },
  async getMe() { return (await fetch(`${API_BASE}/auth/me`, { headers: getHeaders() })).json(); },
  async getUsers() { return (await fetch(`${API_BASE}/auth/users`, { headers: getHeaders() })).json(); },
  async logout() {
    localStorage.removeItem('bbl_token');
    localStorage.removeItem('bbl_user');
    window.location.href = '/login';
  }
};
