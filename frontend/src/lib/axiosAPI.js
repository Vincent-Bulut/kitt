import { PUBLIC_APP_API_URL } from '$env/static/public';
import axios from 'axios';

/** Shared HTTP client for the KITT API. */
export const instance = axios.create({
	baseURL: PUBLIC_APP_API_URL,
	timeout: 30000,
	headers: { 'Content-Type': 'application/json' }
});

const STATUS_MESSAGES = {
	401: 'Unauthorized',
	403: 'Forbidden',
	405: 'Method not allowed',
	500: 'Internal server error'
};

instance.interceptors.response.use(
	(response) => response,
	(error) => {
		if (error.response) {
			const { status, data } = error.response;
			const detail = data?.detail ? `\n${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}` : '';
			alert(`${STATUS_MESSAGES[status] ?? `Request failed (${status})`}${detail}`);
		} else if (error.request) {
			console.error('No response received:', error.request);
			alert('A network error occurred. Please check your connection.');
		} else {
			console.error('Error setting up request:', error.message);
			alert(`An error occurred while setting up the request: ${error.message}`);
		}
		return Promise.reject(error);
	}
);
