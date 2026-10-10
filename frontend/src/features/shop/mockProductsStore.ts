import { ApiRequestError } from '../../api/client';
import { getActiveMembershipPlanForCurrentUser } from '../membership/api.mock';
import type { Product, ProductDraft, ProductSize, RestockRequest, SizeLabel } from './types';

interface MockProductSize extends ProductSize {}

interface MockProduct {
  id: number;
  name: string;
  description: string;
  basePrice: number;
  image: string;
  active: boolean;
  sizes: MockProductSize[];
}

const STORE_KEY = 'campusleague.mock.products';
const SIZE_ORDER: SizeLabel[] = ['S', 'M', 'L', 'XL'];

function seed(): MockProduct[] {
  return [
    {
      id: 1,
      name: 'Skyline Hoodie',
      description: 'Heavyweight fleece with the club crest.',
      basePrice: 120000,
      image: '',
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
      basePrice: 40000,
      image: '',
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
      basePrice: 25000,
      image: '',
      active: false,
      sizes: [
        { id: 9, size: 'S', stock: 0 },
        { id: 10, size: 'M', stock: 0 },
        { id: 11, size: 'L', stock: 0 },
        { id: 12, size: 'XL', stock: 0 },
      ],
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

export function priceForCurrentUser(basePrice: number): number {
  const plan = getActiveMembershipPlanForCurrentUser();
  if (!plan || plan.merchDiscountPct <= 0) return basePrice;
  return basePrice - Math.floor((basePrice * plan.merchDiscountPct) / 100);
}

export function toPublicProduct(p: MockProduct): Product {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    basePrice: p.basePrice,
    price: priceForCurrentUser(p.basePrice),
    image: p.image,
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
    basePrice: draft.basePrice,
    image: draft.image ?? '',
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
    image: patch.image ?? product.image,
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
