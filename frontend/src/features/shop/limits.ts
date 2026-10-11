/** The most of one product + size a single order may contain. The backend
 * refuses more (docs/API_CONTRACT.md, "Validation limits"), so the cart
 * never lets it get that far: the limit counts what is already in the cart
 * plus what is being added. */
export const MAX_PER_ITEM = 10;

export const LIMIT_REACHED_MESSAGE = `You've reached the limit of ${MAX_PER_ITEM} for this item.`;

export function limitNote(inCart: number): string {
  return `Limit ${MAX_PER_ITEM} per item. You have ${inCart} in your cart.`;
}
