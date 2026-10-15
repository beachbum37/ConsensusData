const usdFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const eurFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' });

export const usd = (v: number | null | undefined) => (v == null ? '—' : usdFmt.format(v));
export const eur = (v: number | null | undefined) => (v == null ? '—' : eurFmt.format(v));
