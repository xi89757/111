/**
 * 在浏览器控制台运行此脚本，导出已登录的 Cookie
 * 步骤：F12 -> Console -> 粘贴并回车 -> 复制输出内容 -> 保存为 cookies.json
 */
(function () {
  const cookies = document.cookie.split(';').map(c => {
    const [name, ...rest] = c.trim().split('=');
    return {
      name: name.trim(),
      value: rest.join('=').trim(),
      domain: location.hostname,
      path: '/',
      secure: location.protocol === 'https:',
      httpOnly: false,
      sameSite: 'Lax',
    };
  });
  const output = JSON.stringify(cookies, null, 2);
  console.log('=== 复制以下内容保存为 cookies.json ===');
  console.log(output);
  console.log('=== 结束 ===');
  // 尝试自动复制到剪贴板
  navigator.clipboard.writeText(output).then(
    () => console.log('✓ 已自动复制到剪贴板'),
    () => console.log('请手动复制上方内容')
  );
})();
