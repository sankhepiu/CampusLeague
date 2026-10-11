/** Where bought merchandise is collected. The server sends `pickup_location`
 * per product; anything older than that field falls back to this. */
export const DEFAULT_PICKUP_LOCATION = 'Student Centre, Room 2';

export function pickupOrDefault(location: string | null | undefined): string {
  return location && location.trim() ? location : DEFAULT_PICKUP_LOCATION;
}
