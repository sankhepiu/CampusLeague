import { ApiRequestError } from '../../api/client';
import { getActiveMembershipPlanForCurrentUser } from '../membership/api.mock';
import type { Product, ProductCategory, ProductDraft, ProductSize, RestockRequest, SizeLabel } from './types';

interface MockProductSize extends ProductSize {}

interface MockProduct {
  id: number;
  name: string;
  description: string;
  category: ProductCategory;
  basePrice: number;
  salePct: number;
  imageUrl: string | null;
  active: boolean;
  sizes: MockProductSize[];
}

/** Stand-ins for the backend's /media/products/*.png in mock mode, where
 * there is no server to fetch from: tiny inline SVGs drawn on a 16x16 grid
 * in the same colours as the seed's pixel art. */
function pixelSvg(body: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges"><rect width="16" height="16" fill="#212529"/>${body}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const MOCK_PRODUCT_IMAGES: Record<string, string> = {
  'Skyline Hoodie': pixelSvg(
    '<path fill="#3062c9" d="M4 2h8v2h3v5h-2v5H3V9H1V4h3z"/><path fill="#78a4f0" d="M5 2h6v1H5zM7 6h2v3H7z"/><path fill="#1e3e8c" d="M6 3h4v2H6zM6 11h4v2H6z"/>',
  ),
  'Campus Tee': pixelSvg(
    '<path fill="#e25c36" d="M3 3h3v1h4V3h3l3 3-2 2-2-1v7H5V7L3 8 1 6z"/><path fill="#ffcd56" d="M7 8h2v2H7z"/><path fill="#a0381e" d="M5 13h6v1H5z"/>',
  ),
};

const STORE_KEY = 'campusleague.mock.products';
const SIZE_ORDER: SizeLabel[] = ['S', 'M', 'L', 'XL'];

function seed(): MockProduct[] {
  return [
    {
      id: 1,
      name: 'Skyline Hoodie',
      description: 'Heavyweight fleece with the club crest.',
      category: 'apparel',
      basePrice: 120000,
      salePct: 0,
      imageUrl: MOCK_PRODUCT_IMAGES['Skyline Hoodie'],
      active: true,
      sizes: [
        { id: 1, size: 'S', stock: 8 },
        { id: 2, size: 'M', stock: 5 },
        { id: 3, size: 'L', stock: 6 },
        { id: 4, size: 'XL', stock: 1 },
      ],
    },
    {
      id: 2,
      name: 'Campus Tee',
      description: 'Lightweight cotton tee, screen-printed logo.',
      category: 'apparel',
      basePrice: 40000,
      salePct: 20,
      imageUrl: MOCK_PRODUCT_IMAGES['Campus Tee'],
      active: true,
      sizes: [
        { id: 5, size: 'S', stock: 0 },
        { id: 6, size: 'M', stock: 20 },
        { id: 7, size: 'L', stock: 15 },
        { id: 8, size: 'XL', stock: 10 },
      ],
    },
    {
      id: 3,
      name: 'Archived Cap',
      description: 'Last year’s design — no longer for sale.',
      category: 'accessories',
      basePrice: 25000,
      salePct: 0,
      imageUrl: null,
      active: false,
      sizes: [
        { id: 9, size: 'S', stock: 0 },
        { id: 10, size: 'M', stock: 0 },
        { id: 11, size: 'L', stock: 0 },
        { id: 12, size: 'XL', stock: 0 },
      ],
    },
    {
      id: 4,
      name: 'Skyline Mug',
      description: 'Ceramic mug with the club crest.',
      category: 'drinkware',
      basePrice: 30000,
      salePct: 0,
      imageUrl: null,
      active: true,
      sizes: [{ id: 13, size: 'ONE', stock: 25 }],
    },
  ];
}

function loadStore(): MockProduct[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockProduct[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seed();
  saveStore(seeded);
  return seeded;
}

function saveStore(products: MockProduct[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(products));
  } catch {
    /* storage unavailable */
  }
}

/** base_price, less the sale, less the plan's merch discount if active —
 * in that order, each step rounded down, matching the contract. */
export function priceForCurrentUser(basePrice: number, salePct = 0): number {
  const afterSale = basePrice - Math.floor((basePrice * salePct) / 100);
  const plan = getActiveMembershipPlanForCurrentUser();
  if (!plan || plan.merchDiscountPct <= 0) return afterSale;
  return afterSale - Math.floor((afterSale * plan.merchDiscountPct) / 100);
}

export function toPublicProduct(p: MockProduct): Product {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    category: p.category ?? 'apparel',
    basePrice: p.basePrice,
    salePct: p.salePct ?? 0,
    price: priceForCurrentUser(p.basePrice, p.salePct),
    // `??` also covers a store saved before imageUrl existed.
    imageUrl: p.imageUrl ?? MOCK_PRODUCT_IMAGES[p.name] ?? null,
    active: p.active,
    sizes: p.sizes,
  };
}

export function listMockProducts(): MockProduct[] {
  return loadStore();
}

export function getMockProduct(id: number): MockProduct | undefined {
  return loadStore().find((p) => p.id === id);
}

export function getMockProductSize(sizeId: number): { product: MockProduct; size: MockProductSize } | undefined {
  for (const product of loadStore()) {
    const size = product.sizes.find((s) => s.id === sizeId);
    if (size) return { product, size };
  }
  return undefined;
}

function nextId(ids: number[]): number {
  return ids.reduce((max, id) => Math.max(max, id), 0) + 1;
}

export function createMockProduct(draft: ProductDraft): MockProduct {
  const products = loadStore();
  if (products.some((p) => p.name.toLowerCase() === draft.name.toLowerCase())) {
    throw new ApiRequestError({
      code: 'validation_error',
      message: 'A product with this name already exists.',
      field: 'name',
      errors: [{ field: 'name', code: 'name_taken', message: 'A product with this name already exists.' }],
    });
  }
  const sizeId0 = nextId(products.flatMap((p) => p.sizes.map((s) => s.id)));
  const product: MockProduct = {
    id: nextId(products.map((p) => p.id)),
    name: draft.name,
    description: draft.description ?? '',
    category: draft.category ?? 'apparel',
    basePrice: draft.basePrice,
    salePct: draft.salePct ?? 0,
    // No upload endpoint in the contract: new products have no picture.
    imageUrl: null,
    active: draft.active ?? true,
    // New products start with all four sizes at zero stock (contract Assumption).
    sizes: SIZE_ORDER.map((size, i) => ({ id: sizeId0 + i, size, stock: 0 })),
  };
  products.push(product);
  saveStore(products);
  return product;
}

export function updateMockProduct(id: number, patch: Partial<ProductDraft>): MockProduct {
  const products = loadStore();
  const product = products.find((p) => p.id === id);
  if (!product) throw new ApiRequestError({ code: 'not_found', message: 'No such product.' });

  if (patch.name !== undefined && patch.name.toLowerCase() !== product.name.toLowerCase()) {
    if (products.some((p) => p.id !== id && p.name.toLowerCase() === patch.name!.toLowerCase())) {
      throw new ApiRequestError({
        code: 'validation_error',
        message: 'A product with this name already exists.',
        field: 'name',
        errors: [{ field: 'name', code: 'name_taken', message: 'A product with this name already exists.' }],
      });
    }
  }

  Object.assign(product, {
    name: patch.name ?? product.name,
    basePrice: patch.basePrice ?? product.basePrice,
    description: patch.description ?? product.description,
    category: patch.category ?? product.category,
    salePct: patch.salePct ?? product.salePct,
    active: patch.active ?? product.active,
  });
  saveStore(products);
  return product;
}

export function restockMockProduct(id: number, { size, quantity }: RestockRequest): MockProduct {
  const products = loadStore();
  const product = products.find((p) => p.id === id);
  if (!product) throw new ApiRequestError({ code: 'not_found', message: 'No such product.' });
  const row = product.sizes.find((s) => s.size === size);
  if (!row) throw new ApiRequestError({ code: 'validation_error', message: 'Unknown size.', field: 'size' });
  row.stock += quantity;
  saveStore(products);
  return product;
}

/** Synchronous read-check-write with no `await` in between, same caveat as
 * the events mock: true concurrent-purchase correctness is the server's
 * row-lock guarantee, not something this mock can replicate across tabs. */
export function reserveMockStock(sizeId: number, quantity: number): void {
  const products = loadStore();
  for (const product of products) {
    const size = product.sizes.find((s) => s.id === sizeId);
    if (size) {
      size.stock -= quantity;
      break;
    }
  }
  saveStore(products);
}
