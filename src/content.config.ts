import { z, defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';

const articles = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/articles' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    date: z.coerce.date(),
    tournament: z.string(),
    tour: z.enum(['PGA Tour', 'DP World Tour', 'LIV Golf', 'Major', 'Other']),
    course: z.string().optional(),
    winner: z.string().optional(),
    winnerScore: z.string().optional(),
    isMajor: z.boolean().default(false),
    tags: z.array(z.string()).default([]),
    // Picks cross-reference
    picks: z.array(z.object({
      player: z.string(),
      result: z.enum(['win', 'top5', 'top10', 'top20', 'miss', 'pending']).default('pending'),
      note: z.string().optional(),
    })).optional(),
    // Next week preview
    nextTournament: z.string().optional(),
    nextTournamentDate: z.string().optional(),
    nextTournamentCourse: z.string().optional(),
  }),
});

export const collections = { articles };
