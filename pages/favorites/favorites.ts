import { getFavoriteRecipes, RecipeSummary } from '../../services/mock-api'

Page({
  data: { recipes: [] as RecipeSummary[] },
  onShow() { this.setData({ recipes: getFavoriteRecipes() }) },
  openRecipe(event: WechatMiniprogram.TouchEvent) { wx.navigateTo({ url: `/pages/detail/detail?id=${event.currentTarget.dataset.id}` }) },
})
