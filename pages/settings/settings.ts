Page({
  data: { excludeText: '', pantryText: '', saved: false },
  onLoad() {
    const settings = wx.getStorageSync('userSettings') || {}
    this.setData({ excludeText: settings.excludeText || '', pantryText: settings.pantryText || '' })
  },
  onExcludeInput(event: WechatMiniprogram.Input) { this.setData({ excludeText: event.detail.value, saved: false }) },
  onPantryInput(event: WechatMiniprogram.Input) { this.setData({ pantryText: event.detail.value, saved: false }) },
  save() {
    wx.setStorageSync('userSettings', { excludeText: this.data.excludeText.trim(), pantryText: this.data.pantryText.trim() })
    this.setData({ saved: true })
    wx.showToast({ title: '已保存', icon: 'success' })
  },
  clear() {
    wx.removeStorageSync('userSettings')
    this.setData({ excludeText: '', pantryText: '', saved: false })
  },
  simulateFailure() {
    wx.setStorageSync('mockFailNextRequest', true)
    wx.showToast({ title: '下一次推荐会模拟失败', icon: 'none' })
  },
})
