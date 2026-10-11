import { useEffect, useState } from 'react';
import { request, session, type ClubOption } from '../../api/client';

/** The clubs as the backend's settings list them (GET /clubs). Used until
 * that request answers, and if it cannot be made at all (mock mode, or the
 * server is down), so the badge never has to wait or go missing. */
const KNOWN_CLUBS: ClubOption[] = [
  { slug: 'skyline', name: 'Skyline Student Association', short: 'SSA', color: '#f5c542' },
  { slug: 'robotics', name: 'Pixel Robotics Club', short: 'PRC', color: '#4fd1c5' },
  { slug: 'music', name: 'Raaga Music Society', short: 'RMS', color: '#f472b6' },
];
const DEFAULT_CLUB = KNOWN_CLUBS[0];

/** Fetched once per page load and shared: every TopBar render reuses it. */
let clubsRequest: Promise<ClubOption[]> | null = null;

function loadClubs(): Promise<ClubOption[]> {
  clubsRequest ??= request<ClubOption[]>('/clubs').catch(() => KNOWN_CLUBS);
  return clubsRequest;
}

function find(clubs: ClubOption[], slug: string | null): ClubOption {
  return clubs.find((club) => club.slug === slug) ?? KNOWN_CLUBS.find((club) => club.slug === slug) ?? DEFAULT_CLUB;
}

/** The club this session is in: the slug the session stored at login,
 * looked up in the club list. No slug stored means Skyline, which is also
 * what the server assumes for a request without X-Club.
 *
 * `sessionKey` is anything that changes when the user logs in or out (the
 * user's id), so the club is read again after a login into another club.
 *
 * Also sets `--club-accent` on the document root to the club's colour. */
export function useCurrentClub(sessionKey: unknown): ClubOption {
  const slug = session.getClub();
  const [clubs, setClubs] = useState<ClubOption[]>(KNOWN_CLUBS);

  useEffect(() => {
    let cancelled = false;
    void loadClubs().then((list) => {
      if (!cancelled && Array.isArray(list) && list.length > 0) setClubs(list);
    });
    return () => {
      cancelled = true;
    };
  }, [sessionKey]);

  const club = find(clubs, slug);

  useEffect(() => {
    document.documentElement.style.setProperty('--club-accent', club.color);
  }, [club.color]);

  return club;
}
