import { createPreviewSession, getNextRecommendation, RecipeSummary } from '../../services/mock-api'

type IndexState = 'form' | 'loading' | 'result' | 'empty' | 'error'

Page({
  data: {
    state: 'form' as IndexState,
    selectedTaste: '',
    selectedForm: '',
    priorityIngredient: '',
    pantryOnly: false,
    tastes: [
      { value: '', label: '都可以' },
      { value: 'taste_savory', label: '咸鲜' },
      { value: 'taste_light', label: '清淡' },
      { value: 'taste_spicy', label: '来点辣' },
      { value: 'taste_sweet', label: '偏甜' },
    ],
    forms: [
      { value: '', label: '不限' },
      { value: 'dish', label: '一道菜' },
      { value: 'staple', label: '一碗解决' },
      { value: 'soup', label: '喝点汤' },
    ],
    recipe: null as RecipeSummary | null,
    sessionId: '',
    revision: 0,
    seenCount: 0,
    favorite: false,
    errorMessage: '',
  },

  onShow() {
    if (this.data.recipe) {
      const favorites = wx.getStorageSync('favoriteRecipeIds') || []
      this.setData({ favorite: favorites.includes(this.data.recipe.recipeId) })
    }
  },

  chooseTaste(event: WechatMiniprogram.TouchEvent) {
    this.setData({ selectedTaste: event.currentTarget.dataset.value })
  },

  chooseForm(event: WechatMiniprogram.TouchEvent) {
    this.setData({ selectedForm: event.currentTarget.dataset.value })
  },

  onIngredientInput(event: WechatMiniprogram.Input) {
    this.setData({ priorityIngredient: event.detail.value.trim() })
  },

  togglePantryOnly() {
    this.setData({ pantryOnly: !this.data.pantryOnly })
  },

  async startRecommendation() {
    this.setData({ state: 'loading', errorMessage: '' })
    try {
      const session = await createPreviewSession({
        tastes: this.data.selectedTaste ? [this.data.selectedTaste] : [],
        mealForms: this.data.selectedForm ? [this.data.selectedForm] : [],
        priorityIngredient: this.data.priorityIngredient,
        pantryOnly: this.data.pantryOnly,
        ownedIngredients: ((wx.getStorageSync('userSettings') || {}).pantryText || '')
          .split(/[、,，\s]+/)
          .filter(Boolean),
        excludedIngredients: ((wx.getStorageSync('userSettings') || {}).excludeText || '')
          .split(/[、,，\s]+/)
          .filter(Boolean),
      })
      this.setData({ sessionId: session.sessionId, revision: session.revision })
      await this.loadNext(session.sessionId, session.revision)
    } catch (error) {
      this.setData({ state: 'error', errorMessage: '没有连上推荐服务，请稍后再试。' })
    }
  },

  async loadNext(sessionId?: string, revision?: number) {
    const activeSessionId = sessionId || this.data.sessionId
    const activeRevision = revision || this.data.revision
    this.setData({ state: 'loading' })
    try {
      const response = await getNextRecommendation(activeSessionId, activeRevision)
      if (!response.recipe) {
        this.setData({ state: 'empty', revision: response.revision })
        return
      }
      const favorites = wx.getStorageSync('favoriteRecipeIds') || []
      this.setData({
        state: 'result',
        recipe: response.recipe,
        revision: response.revision,
        seenCount: this.data.seenCount + 1,
        favorite: favorites.includes(response.recipe.recipeId),
      })
    } catch (error) {
      this.setData({ state: 'error', errorMessage: '这次推荐没有完成，条件已经为你保留。' })
    }
  },

  swapRecipe() { this.loadNext() },

  toggleFavorite() {
    if (!this.data.recipe) return
    const ids: string[] = wx.getStorageSync('favoriteRecipeIds') || []
    const next = ids.includes(this.data.recipe.recipeId)
      ? ids.filter(id => id !== this.data.recipe!.recipeId)
      : [...ids, this.data.recipe.recipeId]
    wx.setStorageSync('favoriteRecipeIds', next)
    this.setData({ favorite: !this.data.favorite })
    wx.showToast({ title: this.data.favorite ? '已收藏' : '已取消', icon: 'none' })
  },

  acceptRecipe() {
    if (!this.data.recipe) return
    wx.setStorageSync('activeRecipeId', this.data.recipe.recipeId)
    wx.navigateTo({ url: `/pages/detail/detail?id=${this.data.recipe.recipeId}&accepted=1` })
  },

  openFavorites() { wx.navigateTo({ url: '/pages/favorites/favorites' }) },
  openSettings() { wx.navigateTo({ url: '/pages/settings/settings' }) },
  editConditions() { this.setData({ state: 'form', recipe: null, seenCount: 0 }) },
  retry() { this.data.sessionId ? this.loadNext() : this.startRecommendation() },
})
