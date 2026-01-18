import {instance} from "$lib/axiosAPI.js";

export async function load({ url }) {
  try {
    const response = await instance.get('/referential/assets');

    console.log('Response list of assets:', response);

    return {
      props: { assets: response.data || [] },
    };
  } catch (error) {
    console.error(error);
    return {
      props: { assets: [] },
      // @ts-ignore
      error: error.message
    };
  }
}