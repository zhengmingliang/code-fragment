import React, { useState, useEffect } from 'react';
import { Printer, FileText, AlertCircle, Share2, CheckCircle } from 'lucide-react';
import { numberToChinese } from './utils';

export default function App() {
  const [formData, setFormData] = useState({
    lenderName: '',
    lenderId: '',
    borrowerName: '',
    borrowerId: '',
    borrowerAddress: '',
    amount: '',
    purpose: '购买房屋',
    transferDate: new Date().toISOString().split('T')[0],
    repaymentDate: '',
    interestRate: '',
    borrowerBank: '',
    borrowerAccount: '',
    lenderBank: '',
    lenderAccount: '',
  });

  const [copied, setCopied] = useState(false);
  const [shareLink, setShareLink] = useState('');

  // 页面加载时，尝试从 URL 中读取数据
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const dataParam = params.get('d');
    if (dataParam) {
      try {
        // 解码 Base64 并解析 JSON (处理中文)
        const decodedData = JSON.parse(decodeURIComponent(atob(dataParam)));
        setFormData((prev) => ({ ...prev, ...decodedData }));
      } catch (error) {
        console.error('解析分享链接失败', error);
      }
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handlePrint = () => {
    window.print();
  };

  const fallbackCopyTextToClipboard = (text: string) => {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    // 避免页面滚动
    textArea.style.top = "0";
    textArea.style.left = "0";
    textArea.style.position = "fixed";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      const successful = document.execCommand('copy');
      if (successful) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch (err) {
      console.error('Fallback复制失败', err);
    }
    document.body.removeChild(textArea);
  };

  const handleShare = async () => {
    try {
      // 将表单数据转为 JSON，处理中文后进行 Base64 编码
      const encodedData = btoa(encodeURIComponent(JSON.stringify(formData)));
      
      // 构建分享链接
      const shareUrl = `${window.location.origin}${window.location.pathname}?d=${encodedData}`;
      setShareLink(shareUrl);
      
      // 尝试使用现代 Clipboard API (需要 HTTPS 或 localhost)
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(shareUrl);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } else {
        // 如果在非安全环境下（如局域网 IP），使用传统方法降级处理
        fallbackCopyTextToClipboard(shareUrl);
      }
    } catch (error) {
      console.error('生成链接失败', error);
    }
  };

  const amountNum = parseFloat(formData.amount);
  const amountChinese = !isNaN(amountNum) && amountNum > 0 ? numberToChinese(amountNum) : '';

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col md:flex-row font-sans">
      {/* Left Sidebar - Form (Hidden on Print) */}
      <div className="w-full md:w-1/3 lg:w-1/4 bg-white border-r border-gray-200 p-6 overflow-y-auto no-print shadow-lg z-10 h-screen sticky top-0">
        <div className="flex items-center gap-2 mb-6">
          <FileText className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold text-gray-800">借条生成器</h1>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6 text-sm text-blue-800 flex gap-2">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <p>请在下方填写借款信息，右侧将实时生成具有法律效力的标准借条。核对无误后可直接打印。</p>
        </div>

        <form className="space-y-6">
          {/* 借款人信息 */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-900 border-b pb-2">借款人信息（欠钱方）</h2>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">姓名</label>
              <input type="text" name="borrowerName" value={formData.borrowerName} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="张三" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">身份证号</label>
              <input type="text" name="borrowerId" value={formData.borrowerId} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="11010519900101XXXX" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">常住/送达地址（防失联必填）</label>
              <input type="text" name="borrowerAddress" value={formData.borrowerAddress} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="北京市朝阳区XXX小区X号楼X单元XXX" />
            </div>
          </div>

          {/* 出借人信息 */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-900 border-b pb-2">出借人信息（给钱方）</h2>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">姓名</label>
              <input type="text" name="lenderName" value={formData.lenderName} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="李四" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">身份证号</label>
              <input type="text" name="lenderId" value={formData.lenderId} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="11010519800101XXXX" />
            </div>
          </div>

          {/* 借款详情 */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-900 border-b pb-2">借款详情</h2>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">借款金额（元）</label>
              <input type="number" name="amount" value={formData.amount} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="留空则打印后手写" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">借款用途</label>
              <input type="text" name="purpose" value={formData.purpose} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="购买房屋" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">借款日期</label>
                <input type="date" name="transferDate" value={formData.transferDate} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">还款日期</label>
                <input type="date" name="repaymentDate" value={formData.repaymentDate} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">年利率（%）</label>
              <input type="number" name="interestRate" value={formData.interestRate} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="留空则打印后手写" step="0.1" />
              <p className="text-xs text-gray-500 mt-1">无利息请填0，受法律保护的最高年利率通常为LPR的4倍。</p>
            </div>
          </div>

          {/* 账户信息 */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-900 border-b pb-2">转账与收款账户（强烈建议填写）</h2>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">借款人收款账户（出借人打款至此）</label>
              <input type="text" name="borrowerBank" value={formData.borrowerBank} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm mb-2" placeholder="开户行，如：工商银行北京分行" />
              <input type="text" name="borrowerAccount" value={formData.borrowerAccount} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="银行账号" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">出借人收款账户（借款人还款至此）</label>
              <input type="text" name="lenderBank" value={formData.lenderBank} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm mb-2" placeholder="开户行，如：建设银行上海分行" />
              <input type="text" name="lenderAccount" value={formData.lenderAccount} onChange={handleChange} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" placeholder="银行账号" />
            </div>
          </div>
        </form>

        <div className="mt-8 pt-6 border-t border-gray-200 pb-8 space-y-3">
          <button
            onClick={handleShare}
            className={`w-full font-medium py-3 px-4 rounded-md flex items-center justify-center gap-2 transition-colors ${
              copied ? 'bg-green-100 text-green-700 border border-green-300' : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            {copied ? (
              <>
                <CheckCircle className="w-5 h-5" />
                链接已复制，可发送给对方
              </>
            ) : (
              <>
                <Share2 className="w-5 h-5" />
                生成分享链接
              </>
            )}
          </button>

          {shareLink && (
            <div className="p-3 bg-gray-50 border border-gray-200 rounded-md mt-2">
              <p className="text-xs text-gray-500 mb-1">如果自动复制失败，请手动复制以下链接：</p>
              <input 
                type="text" 
                readOnly 
                value={shareLink} 
                className="w-full text-xs p-2 border border-gray-300 rounded bg-white text-gray-600 focus:outline-none focus:border-blue-500"
                onFocus={(e) => e.target.select()}
              />
            </div>
          )}
          
          <button
            onClick={handlePrint}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-md flex items-center justify-center gap-2 transition-colors"
          >
            <Printer className="w-5 h-5" />
            打印借条
          </button>
        </div>
      </div>

      {/* Right Content - Document Preview */}
      <div className="flex-1 p-4 md:p-8 overflow-y-auto print-container flex justify-center">
        {/* A4 Paper Container */}
        <div className="bg-white shadow-xl w-full max-w-[210mm] min-h-[297mm] p-[15mm] md:p-[20mm] print:p-0 print:shadow-none print:min-h-0 print-container font-serif-zh text-black leading-relaxed print:leading-normal">
          
          <h1 className="text-3xl print:text-2xl font-bold text-center mb-8 print:mb-4 tracking-[0.5em]">借条</h1>

          <div className="space-y-3 print:space-y-2 mb-6 print:mb-4 text-base print:text-[14px]">
            <div className="flex flex-wrap gap-x-8 gap-y-2">
              <p><span className="font-bold">出借人（债权人）：</span><span className="border-b border-black px-2 min-w-[100px] inline-block text-center">{formData.lenderName || '　　　　'}</span></p>
              <p><span className="font-bold">身份证号：</span><span className="border-b border-black px-2 min-w-[200px] inline-block text-center">{formData.lenderId || '　　　　　　　　　　'}</span></p>
            </div>
            <div className="flex flex-wrap gap-x-8 gap-y-2">
              <p><span className="font-bold">借款人（债务人）：</span><span className="border-b border-black px-2 min-w-[100px] inline-block text-center">{formData.borrowerName || '　　　　'}</span></p>
              <p><span className="font-bold">身份证号：</span><span className="border-b border-black px-2 min-w-[200px] inline-block text-center">{formData.borrowerId || '　　　　　　　　　　'}</span></p>
            </div>
          </div>

          <div className="space-y-5 print:space-y-3 text-base print:text-[14px] text-justify">
            <p className="indent-8">
              <span className="font-bold">一、借款协议：</span>现为<span className="border-b border-black px-2">{formData.purpose || '　　　　　'}</span>需要，借款人向出借人借到人民币（大写）
              <span className="border-b border-black px-2 font-bold min-w-[240px] print:min-w-[180px] inline-block text-center">{amountChinese || '　　　　　　　　　　　　'}</span>
              （小写：¥<span className="border-b border-black px-2 min-w-[120px] print:min-w-[80px] inline-block text-center">{formData.amount || '　　　　　　'}</span>元）。借款人承诺不将借款用于任何非法活动。
            </p>

            <p className="indent-8">
              <span className="font-bold">二、款项交付：</span>出借人于
              <span className="border-b border-black px-2">{formData.transferDate ? new Date(formData.transferDate).getFullYear() : '　　'}</span>年
              <span className="border-b border-black px-2">{formData.transferDate ? new Date(formData.transferDate).getMonth() + 1 : '　'}</span>月
              <span className="border-b border-black px-2">{formData.transferDate ? new Date(formData.transferDate).getDate() : '　'}</span>日
              通过银行转账方式交付全部借款。转账收款账户信息为：
            </p>
            <div className="pl-12 space-y-1 print:space-y-0">
              <p>户名：<span className="border-b border-black px-2">{formData.borrowerName || '　　　　　'}</span></p>
              <p>开户行：<span className="border-b border-black px-2">{formData.borrowerBank || '　　　　　　　　　　'}</span></p>
              <p>账号：<span className="border-b border-black px-2">{formData.borrowerAccount || '　　　　　　　　　　　　　　'}</span></p>
            </div>

            <p className="indent-8">
              <span className="font-bold">三、借款期限及利息：</span>借款期限自实际到账之日起至
              <span className="border-b border-black px-2">{formData.repaymentDate ? new Date(formData.repaymentDate).getFullYear() : '　　'}</span>年
              <span className="border-b border-black px-2">{formData.repaymentDate ? new Date(formData.repaymentDate).getMonth() + 1 : '　'}</span>月
              <span className="border-b border-black px-2">{formData.repaymentDate ? new Date(formData.repaymentDate).getDate() : '　'}</span>日止。
              借款期内年利率为 <span className="border-b border-black px-2 min-w-[40px] inline-block text-center">{formData.interestRate || '　　'}</span>%（未超过合同成立时一年期LPR的4倍）。
            </p>

            <p className="indent-8">
              <span className="font-bold">四、还款方式：</span>借款人应于借款到期日一次性全额归还本金及利息至出借人以下指定账户：
            </p>
            <div className="pl-12 space-y-1 print:space-y-0">
              <p>户名：<span className="border-b border-black px-2">{formData.lenderName || '　　　　　'}</span></p>
              <p>开户行：<span className="border-b border-black px-2">{formData.lenderBank || '　　　　　　　　　　'}</span></p>
              <p>账号：<span className="border-b border-black px-2">{formData.lenderAccount || '　　　　　　　　　　　　　　'}</span></p>
            </div>

            <p className="indent-8">
              <span className="font-bold">五、逾期责任：</span>若借款人未按期足额偿还本金，逾期部分按年利率 <span className="border-b border-black px-2 min-w-[40px] inline-block text-center">{formData.interestRate && parseFloat(formData.interestRate) > 0 ? formData.interestRate : '　　'}</span>% 计收逾期利息。因借款人违约致使出借人采取诉讼等方式实现债权的，出借人为此支付的<span className="font-bold">诉讼费、律师费、保全费、保全担保费、差旅费</span>等实现债权的全部费用由借款人承担。
            </p>

            <p className="indent-8">
              <span className="font-bold">六、送达地址：</span>借款人确认本借条下方载明的常住地址（或身份证载明地址）为法律文书（包括但不限于催款通知、诉讼传票、判决书等）的有效送达地址。地址变更需书面通知出借人，否则按该地址邮寄即视为送达。
            </p>

            <p className="indent-8">
              <span className="font-bold">七、争议解决：</span>本借条履行过程中如发生争议，双方应友好协商；协商不成的，任何一方均有权向出借人所在地人民法院提起诉讼。
            </p>

            <p className="indent-8">
              <span className="font-bold">八、生效及其他：</span><span className="font-bold">若出借人未按约定日期将全部借款足额支付至借款人指定账户，本借条不发生法律效力。</span>本借条一式两份，出借人与借款人各执一份，自借款人（及共同借款人）签字并按捺手印，且出借人实际足额支付借款之日起生效。
            </p>
          </div>

          <div className="mt-8 print:mt-4 text-center text-gray-500 tracking-widest">
            （以下无正文）
          </div>

          <div className="mt-12 print:mt-6 flex flex-col items-end space-y-5 print:space-y-3 pr-8 print:pr-0 print:text-[14px]">
            <p className="flex items-center">
              <span className="font-bold">借款人（签字并捺印）：</span>
              <span className="inline-block w-40 border-b border-black"></span>
            </p>
            <p className="flex items-center">
              <span className="font-bold">联系电话：</span>
              <span className="inline-block w-40 border-b border-black"></span>
            </p>
            <p className="flex items-center">
              <span className="font-bold">常住/送达地址：</span>
              <span className="inline-block w-64 border-b border-black text-center">{formData.borrowerAddress || '　　　　　　　　　　　　　　'}</span>
            </p>
            <p className="mt-6 print:mt-4">
              <span className="inline-block w-12 border-b border-black text-center"></span> 年 
              <span className="inline-block w-8 border-b border-black text-center ml-2"></span> 月 
              <span className="inline-block w-8 border-b border-black text-center ml-2"></span> 日
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}
