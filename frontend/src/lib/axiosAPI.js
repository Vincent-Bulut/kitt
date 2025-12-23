// lib/axiosAPI.js
import {PUBLIC_APP_API_URL} from "$env/static/public";

import axios from 'axios';
import {browser} from "$app/environment";
import {error, json} from "@sveltejs/kit";

// Crée une instance d'Axios avec une configuration par défaut
export const instance = axios.create({
    baseURL: PUBLIC_APP_API_URL,
    timeout: 30000, // Délai d'attente par défaut (en millisecondes)
    headers: {
        'Content-Type': 'application/json',
        // Ajoutez d'autres en-têtes par défaut ici si nécessaire
    },
});


// Ajouter un intercepteur de requête (facultatif)
instance.interceptors.request.use(function (config) {
    // if (!browser) return;
    return config;
}, function (error) {
    return Promise.reject(error);
});


// Ajouter un intercepteur de réponse (facultatif)
instance.interceptors.response.use(
  function (response) {
    return response;
  },
  function (error) {
    if (error.response) {
      const { status, data, headers } = error.response;
      let errorMessage = '';

      switch (status) {
        case 401:
          errorMessage = "Unauthorized";
          break;
        case 403:
          errorMessage = "Forbidden";
          break;
        case 405:
          errorMessage = "Method not allowed";
          break;
        case 500:
          errorMessage = "Internal server error";
          break;
        default:
          console.log(`Unexpected error: ${status}`);
          break;
      }

      if (errorMessage) {
        alert(errorMessage);
      } else {
        console.log(`Status: ${status}`, `Data: ${JSON.stringify(data)}`, `Headers: ${JSON.stringify(headers)}`);
        alert(`An unexpected error occurred: \nCode: ${status}\nData: ${JSON.stringify(data)}\nHeaders: ${JSON.stringify(headers)}`);
      }
    } else if (error.request) {
      console.log('No response received:', error.request);
      alert('A network error occurred. Please check your connection.');
    } else {
      console.error('Error setting up request:', error.message);
      alert(`An error occurred while setting up the request: ${error.message}`);
    }

    return Promise.reject(error);
  }
);

