import { getRecipe, RecipeSummary } from '../../services/mock-api'

Page({
  data: {
    recipe: null as RecipeSummary | null,
    accepted: false,
    favorite: false,
    cooked: false,
    tab: 'ingredients',
  },
  onLoad(query: Record<string, string>) {
    const recipe = getRecipe(query.id)
    if (!recipe) {
      wx.showToast({ title: '这个做法暂不可用', icon: 'none' })
      setTimeout(() => wx.navigateBack(), 800)
      return
    }
    const favorites: string[] = wx.getStorageSync('favoriteRecipeIds') || []
    const cooked: string[] = wx.getStorageSync('cookedRecipeIds') || []
    this.setData({ recipe, accepted: query.accepted === '1', favorite: favorites.includes(recipe.recipeId), cooked: cooked.includes(recipe.recipeId) })
  },
  selectTab(event: WechatMiniprogram.TouchEvent) { this.setData({ tab: event.currentTarget.dataset.tab }) },
  toggleFavorite() {
    if (!this.data.recipe) return
    const ids: string[] = wx.getStorageSync('favoriteRecipeIds') || []
    const next = ids.includes(this.data.recipe.recipeId) ? ids.filter(id => id !== this.data.recipe!.recipeId) : [...ids, this.data.recipe.recipeId]
    wx.setStorageSync('favoriteRecipeIds', next)
    this.setData({ favorite: !this.data.favorite })
  },
  markCooked() {
    if (!this.data.recipe || this.data.cooked) return
    const ids: string[] = wx.getStorageSync('cookedRecipeIds') || []
    wx.setStorageSync('cookedRecipeIds', [...ids, this.data.recipe.recipeId])
    this.setData({ cooked: true })
    wx.showToast({ title: '记下啦', icon: 'success' })
  },
  copySource() {
    if (!this.data.recipe) return
    wx.setClipboardData({ data: this.data.recipe.sourceUrl })
  },
})
