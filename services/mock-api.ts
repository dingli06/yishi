export interface RecipeSummary {
  recipeId: string
  version: string
  dishId: string
  title: string
  glyph: string
  tone: string
  mealForm: string
  mealFormLabel: string
  sourceMinutes: number
  servingNote: string
  prerequisite: string
  reasons: string[]
  tasteIds: string[]
  ingredients: Array<{ name: string; amount: string; optional?: boolean }>
  steps: string[]
  sourceUrl: string
}

interface PreviewConditions {
  tastes: string[]
  mealForms: string[]
  priorityIngredient: string
  pantryOnly: boolean
  ownedIngredients: string[]
  excludedIngredients: string[]
}

const RECIPES: RecipeSummary[] = [
  {
    recipeId: 'recipe_2ed5fd46169858cb95a95b65169fdc41', version: 'rv_d5331004cde15e9f72f2d9aa', dishId: 'dish_94970bd943f857d5b8c8380f20ee18d3',
    title: '凉拌黄瓜', glyph: '凉', tone: 'green', mealForm: 'dish', mealFormLabel: '一道菜', sourceMinutes: 20,
    servingNote: '不是完整一餐，按需要搭配主食', prerequisite: '步骤包含 15 分钟腌制；来源时间尚未实烹核验。',
    reasons: ['清爽的酸香口味', '黄瓜是主要食材', '开发样板已完成 agent 对照'], tasteIds: ['taste_sour','taste_light'],
    ingredients: [{name:'黄瓜',amount:'200 克 × 份数'},{name:'醋',amount:'7.5 ml + 4 ml × 份数'},{name:'酱油',amount:'5 ml + 2.5 ml × 份数'},{name:'蒜',amount:'3 瓣 × 份数'},{name:'盐',amount:'0.4 克 + 0.2 克 × 份数'},{name:'香油',amount:'5 ml + 2 ml × 份数'},{name:'蚝油',amount:'5 ml'},{name:'白糖',amount:'原文步骤为 5 克'}],
    steps:['用菜刀将黄瓜拍扁，再剁成长 3 厘米的碎块。','将碎黄瓜装入碗中，蒜拍碎切成末。','放入白糖，搅拌均匀腌制 15 分钟。','依次放入醋、酱油、盐、蚝油和蒜，搅拌均匀。','倒入香油并均匀搅拌。'],
    sourceUrl:'https://raw.githubusercontent.com/Anduin2017/HowToCook/0e106eea348c734fe1586f781202994439cf98a5/dishes/vegetable_dish/%E5%87%89%E6%8B%8C%E9%BB%84%E7%93%9C.md',
  },
  {
    recipeId:'recipe_10816142bd1952fe9a6f678dcfec17c6', version:'rv_39325dd545404e1278fe5581', dishId:'dish_0ddbdc32199d57b8ad3192d1b20c2143',
    title:'西红柿炒鸡蛋', glyph:'鲜', tone:'orange', mealForm:'dish', mealFormLabel:'一道菜', sourceMinutes:15,
    servingNote:'下饭菜，记得另配主食', prerequisite:'15 分钟是来源估计，不是经过核验的严格总时间。', reasons:['咸鲜家常口味','西红柿与鸡蛋都是主要食材','具体做法版本已固定'], tasteIds:['taste_savory'],
    ingredients:[{name:'西红柿',amount:'1 个（约 180g）× 份数'},{name:'鸡蛋',amount:'1.5 个 × 份数，向上取整'},{name:'食用油',amount:'4 ml × 鸡蛋数'},{name:'盐',amount:'1.5–2g × 份数'},{name:'糖',amount:'0–2g × 份数',optional:true},{name:'葱花',amount:'0–10g × 份数',optional:true}],
    steps:['西红柿洗净、去蒂，切成不超过 4cm 的小块。','鸡蛋打入碗中，加一部分盐搅匀。','热锅加油，倒入鸡蛋液，炒至凝固微黄后盛出。','原锅加入西红柿，翻炒至软烂。','倒回鸡蛋，加入剩余盐及所选可选调味，炒匀盛盘。'],
    sourceUrl:'https://raw.githubusercontent.com/Anduin2017/HowToCook/0e106eea348c734fe1586f781202994439cf98a5/dishes/vegetable_dish/%E8%A5%BF%E7%BA%A2%E6%9F%BF%E7%82%92%E9%B8%A1%E8%9B%8B.md',
  },
  {
    recipeId:'recipe_5699dacb1d3857489d96592e745afc28', version:'rv_0fecdee637ab30328da4e42a', dishId:'dish_c5e23a930bbc54a29aa5e3d4b28159f9',
    title:'蛋炒饭', glyph:'饭', tone:'yellow', mealForm:'staple', mealFormLabel:'一碗解决', sourceMinutes:25,
    servingNote:'主食版本，可作为一餐形态', prerequisite:'需要已经煮熟并冷却的米饭；若从生米开始须另计时间。', reasons:['一碗就能解决一餐','优先利用冷饭和鸡蛋','来源提供了完整操作步骤'], tasteIds:['taste_savory'],
    ingredients:[{name:'冷饭',amount:'500 ml × 份数'},{name:'鸡蛋',amount:'按原文公式计算'},{name:'火腿',amount:'2 个 × 份数'},{name:'食用油',amount:'12 ml × 份数'},{name:'盐',amount:'4–6g × 份数'},{name:'生抽',amount:'10 ml × 份数'},{name:'香葱',amount:'1 棵 × 份数'}],
    steps:['米饭提前铲成小块，其他配料按需要切好。','蛋白、蛋黄分开打散。','大火热锅放油，先炒凝固蛋白并盛出。','炒蛋黄和配料，倒回蛋白后加入米饭大火翻炒。','米饭炒散后调小火调味，最后加入香葱翻炒盛出。'],
    sourceUrl:'https://raw.githubusercontent.com/Anduin2017/HowToCook/0e106eea348c734fe1586f781202994439cf98a5/dishes/staple/%E8%9B%8B%E7%82%92%E9%A5%AD.md',
  },
  {
    recipeId:'recipe_5e7f9737dc405ac7a87b328133471d2f', version:'rv_b1d38b6c8ec089e7d651369a', dishId:'dish_2a6f7a82b1fc5558b2cfe329ddf97a55',
    title:'清蒸鲈鱼', glyph:'蒸', tone:'blue', mealForm:'dish', mealFormLabel:'一道菜', sourceMinutes:30,
    servingNote:'下饭菜，记得另配主食', prerequisite:'鲈鱼需要预处理，并腌制 10 分钟以上。', reasons:['清淡鲜美的口味','蒸制做法，版本明确','鲈鱼是主要食材'], tasteIds:['taste_light','taste_savory'],
    ingredients:[{name:'鲈鱼',amount:'1 条'},{name:'香葱',amount:'3 根'},{name:'姜',amount:'1 块'},{name:'食用油',amount:'10–15ml'},{name:'蒸鱼豉油',amount:'10–15ml'},{name:'盐',amount:'5–10g'}],
    steps:['姜切片切丝，香葱分葱白和葱绿处理。','鲈鱼处理、擦干、改刀，用盐腌制 10 分钟以上。','鱼肚和鱼身放姜葱，用筷子将鱼与盘底隔开。','水热后入锅，大火蒸约 10 分钟。','换干净盘子，淋蒸鱼豉油，铺姜葱丝后浇热油。'],
    sourceUrl:'https://raw.githubusercontent.com/Anduin2017/HowToCook/0e106eea348c734fe1586f781202994439cf98a5/dishes/aquatic/%E6%B8%85%E8%92%B8%E9%B2%88%E9%B1%BC/%E6%B8%85%E8%92%B8%E9%B2%88%E9%B1%BC.md',
  },
]

const pause = <T>(value: T, ms = 420) => new Promise<T>(resolve => setTimeout(() => resolve(value), ms))

export async function createPreviewSession(conditions: PreviewConditions) {
  wx.setStorageSync('previewConditions', conditions)
  const sessionId = `preview_${Date.now()}`
  wx.setStorageSync(`session:${sessionId}`, { seen: [], conditions })
  return pause({ sessionId, revision: 1 })
}

export async function getNextRecommendation(sessionId: string, expectedRevision: number) {
  if (wx.getStorageSync('mockFailNextRequest')) {
    wx.removeStorageSync('mockFailNextRequest')
    await pause(null, 280)
    throw new Error('Simulated network failure')
  }
  const session = wx.getStorageSync(`session:${sessionId}`) || { seen: [], conditions: {} }
  const unseen = RECIPES.filter(recipe => !session.seen.includes(recipe.dishId))
  if (!unseen.length) return pause({ recipe: null, revision: expectedRevision })
  const wantedForm = session.conditions.mealForms?.[0]
  let pool = wantedForm ? unseen.filter(recipe => recipe.mealForm === wantedForm) : unseen
  const excluded: string[] = session.conditions.excludedIngredients || []
  pool = pool.filter(recipe => !recipe.ingredients.some(item => excluded.includes(item.name)))
  if (session.conditions.pantryOnly) {
    const owned: string[] = session.conditions.ownedIngredients || []
    pool = pool.filter(recipe => recipe.ingredients
      .filter(item => !item.optional)
      .every(item => owned.includes(item.name)))
  }
  if (!pool.length) return pause({ recipe: null, revision: expectedRevision })
  const wantedTaste = session.conditions.tastes?.[0]
  const priorityIngredient = session.conditions.priorityIngredient
  pool.sort((left, right) => {
    const score = (recipe: RecipeSummary) =>
      (wantedTaste && recipe.tasteIds.includes(wantedTaste) ? 2 : 0) +
      (priorityIngredient && recipe.ingredients.some(item => item.name.includes(priorityIngredient) || priorityIngredient.includes(item.name)) ? 3 : 0)
    return score(right) - score(left)
  })
  const recipe = pool[0]
  session.seen.push(recipe.dishId)
  wx.setStorageSync(`session:${sessionId}`, session)
  return pause({ recipe, revision: expectedRevision + 1 })
}

export function getRecipe(recipeId: string) { return RECIPES.find(item => item.recipeId === recipeId) || null }
export function getFavoriteRecipes() { const ids: string[] = wx.getStorageSync('favoriteRecipeIds') || []; return RECIPES.filter(item => ids.includes(item.recipeId)) }
