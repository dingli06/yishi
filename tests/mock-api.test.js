const assert = require('node:assert/strict')

const storage = new Map()
global.wx = {
  getStorageSync: key => storage.get(key),
  setStorageSync: (key, value) => storage.set(key, value),
  removeStorageSync: key => storage.delete(key),
}

const api = require('../services/mock-api.ts')

async function nextFor(conditions) {
  const session = await api.createPreviewSession(conditions)
  return api.getNextRecommendation(session.sessionId, session.revision)
}

async function run() {
  const defaults = { tastes: [], mealForms: [], priorityIngredient: '', pantryOnly: false, ownedIngredients: [], excludedIngredients: [] }

  const session = await api.createPreviewSession(defaults)
  let revision = session.revision
  const dishes = new Set()
  for (let index = 0; index < 4; index += 1) {
    const result = await api.getNextRecommendation(session.sessionId, revision)
    assert.ok(result.recipe)
    assert.equal(dishes.has(result.recipe.dishId), false, 'a dish must not repeat within a round')
    dishes.add(result.recipe.dishId)
    revision = result.revision
  }
  assert.equal((await api.getNextRecommendation(session.sessionId, revision)).recipe, null)

  const staple = await nextFor({ ...defaults, mealForms: ['staple'] })
  assert.equal(staple.recipe.title, '蛋炒饭')
  assert.equal((await api.getNextRecommendation(staple.recipe ? [...storage.keys()].at(-1)?.replace('session:', '') : '', staple.revision)).recipe, null)

  const strictEmptyPantry = await nextFor({ ...defaults, pantryOnly: true })
  assert.equal(strictEmptyPantry.recipe, null, 'strict pantry must not silently relax')

  const excluded = await nextFor({ ...defaults, excludedIngredients: ['黄瓜'] })
  assert.notEqual(excluded.recipe.title, '凉拌黄瓜')

  const priority = await nextFor({ ...defaults, priorityIngredient: '鸡蛋' })
  assert.equal(priority.recipe.title, '西红柿炒鸡蛋')

  storage.set('mockFailNextRequest', true)
  await assert.rejects(() => nextFor(defaults), /Simulated network failure/)
  assert.equal(storage.has('mockFailNextRequest'), false, 'retry flag must be one-shot')

  console.log('mock-api: 6 scenarios passed')
}

run().catch(error => {
  console.error(error)
  process.exitCode = 1
})
