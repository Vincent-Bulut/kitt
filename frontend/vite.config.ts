import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		// Same URL layout as production (nginx): the browser calls /api/..., forwarded to the API without the prefix
		proxy: {
			'/api': {
				target: 'http://localhost:8000',
				rewrite: (path) => path.replace(/^\/api/, '')
			}
		}
	}
});
