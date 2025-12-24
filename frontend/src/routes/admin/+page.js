

import {instance} from "$lib/axiosAPI.js";

export async function load({ url }) {
  try {
    const response = await instance.get('/admin/portfolios');

    console.log('Response list of portfolios:', response);

    return {
      props: { portfolios: response.data || [] },
    };
  } catch (error) {
    console.error(error);
    return {
      props: { portfolios: [] },
      // @ts-ignore
      error: error.message
    };
  }
}